"""Established systems: modern software that already has its own API (FR-15).

REPLIC8 reads the system's OpenAPI file from its repo and lists the operations so the system shows
in the graph. It never runs the repo's code and never calls the system: established operations
are not in the Registry, so the gateway, MCP and the generated OpenAPI can't serve them.

A re-import replaces the saved entry (no version history). The commit it came from is kept.
Layout: <data_dir>/established/<system>.json
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from .config import Settings
from .events import EventLog
from .ingest import IngestError
from .models import COMMIT, NAME, OP_NAME
from .openapi_spec import MAX_OPERATIONS, SpecError, find_spec, info, load_spec, read_operations
from .registry import Registry, RegistryError, _atomic_write
from .sources import canonical_url, fetch


class EstablishedError(Exception):
    """Safe to show to an admin."""


class ListedOperation(BaseModel):
    name: str
    method: str = Field(pattern=r"^(GET|PUT|POST|DELETE|PATCH|HEAD|OPTIONS|TRACE)$")
    path: str = Field(max_length=300)
    summary: str = Field(max_length=500)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not OP_NAME.match(v):
            raise ValueError("operation name must match ^[a-z][a-z0-9_]{0,63}$")
        return v


class EstablishedSystem(BaseModel):
    system: str
    kind: Literal["established"] = "established"
    parent: bool = False
    repo_url: str = Field(max_length=300)
    source_commit: str
    spec_file: str = Field(max_length=200)
    title: str = Field(default="", max_length=100)
    api_version: str = Field(default="", max_length=50)
    imported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    operations: list[ListedOperation] = Field(max_length=MAX_OPERATIONS)

    @field_validator("system")
    @classmethod
    def _system(cls, v: str) -> str:
        if not NAME.match(v):
            raise ValueError("system must match ^[a-z][a-z0-9_]{0,31}$")
        return v

    @field_validator("source_commit")
    @classmethod
    def _commit(cls, v: str) -> str:
        if not COMMIT.match(v):
            raise ValueError("source_commit must be a full 40-character SHA")
        return v

    def view(self) -> dict[str, Any]:
        return {
            "system": self.system, "kind": self.kind, "parent": self.parent, "repo": self.repo_url,
            "source_commit": self.source_commit, "spec_file": self.spec_file, "title": self.title,
            "api_version": self.api_version, "imported_at": self.imported_at.isoformat(),
            "called_by_replic8": False,
            "operations": [{"tool": f"{self.system}.{op.name}", "method": op.method, "path": op.path,
                            "summary": op.summary, "input_schema": op.input_schema,
                            "output_schema": op.output_schema} for op in self.operations],
        }


class Catalog:
    def __init__(self, data_dir: Path):
        self.root = (data_dir / "established").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, system: str) -> Path:
        if not NAME.match(system):
            raise EstablishedError("invalid system name")
        return self.root / f"{system}.json"

    def save(self, entry: EstablishedSystem) -> None:
        _atomic_write(self._path(entry.system), entry.model_dump_json(indent=2))

    def get(self, system: str) -> EstablishedSystem | None:
        path = self._path(system)
        if not path.is_file():
            return None
        return EstablishedSystem.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def systems(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json") if NAME.match(p.stem))

    def all(self) -> list[EstablishedSystem]:
        return [e for e in (self.get(s) for s in self.systems()) if e is not None]


def legacy_name_taken(registry: Registry, system: str) -> bool:
    try:
        return bool(registry.versions(system))
    except RegistryError:
        return True


class EstablishedImporter:
    """Fetch a repo, read its API file, save the listing. Progress goes to the event log."""

    def __init__(self, settings: Settings, catalog: Catalog, registry: Registry, events: EventLog):
        self.settings = settings
        self.catalog = catalog
        self.registry = registry
        self.events = events
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, system: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(system, threading.Lock())

    def busy(self, system: str) -> bool:
        return self._lock(system).locked()

    def run(self, system: str, repo_url: str, *, parent: bool = False,
            spec_path: str | None = None) -> EstablishedSystem:
        if not NAME.match(system):
            raise EstablishedError("system name must match ^[a-z][a-z0-9_]{0,31}$")
        if not self._lock(system).acquire(blocking=False):
            raise EstablishedError(f"{system} is already being imported")
        try:
            self.events.add("onboard_started", system=system, detail="established")
            try:
                entry = self._run(system, repo_url, parent, spec_path)
            except EstablishedError as exc:
                self.events.add("onboard_failed", system=system, detail=str(exc))
                raise
            self.events.add("listed", system=system, detail="established", operations=len(entry.operations))
            return entry
        finally:
            self._lock(system).release()

    def _run(self, system: str, repo_url: str, parent: bool, spec_path: str | None) -> EstablishedSystem:
        if legacy_name_taken(self.registry, system):
            raise EstablishedError("that name is already used by a legacy system")
        self.events.add("onboard_stage", system=system, detail="fetch")
        try:
            canonical_url(repo_url, self.settings.local_repo_root)
            checkout = fetch(repo_url, self.settings.data_dir / "repos", local_root=self.settings.local_repo_root,
                             max_bytes=self.settings.max_repo_bytes, max_files=self.settings.max_repo_files,
                             timeout_s=self.settings.clone_timeout_s)
        except IngestError as exc:
            raise EstablishedError(str(exc)) from None
        self.events.add("onboard_stage", system=system, detail="read")
        try:
            path = find_spec(checkout.path, spec_path)
            spec = load_spec(path)
            operations = read_operations(spec)
        except SpecError as exc:
            raise EstablishedError(str(exc)) from None
        if not operations:
            raise EstablishedError("the API file lists no operations")
        self.events.add("onboard_stage", system=system, detail="list")
        title, api_version = info(spec)
        try:
            entry = EstablishedSystem(
                system=system, parent=parent, repo_url=checkout.url, source_commit=checkout.commit,
                spec_file=path.resolve().relative_to(checkout.path.resolve()).as_posix()[:200],
                title=title, api_version=api_version,
                operations=[ListedOperation(**op) for op in operations])
        except ValidationError:
            raise EstablishedError("the API file could not be turned into a list of operations") from None
        self.catalog.save(entry)
        return entry
