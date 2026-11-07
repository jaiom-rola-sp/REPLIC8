"""File-based registry of versioned wrappers (FR-3, FR-8).

Layout: <data_dir>/registry/<system>/v<N>.json plus a `current` pointer file.
Versions are append-only; rollback only moves the pointer.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from .models import NAME, ContractTestResult, Operation, WrapperVersion


class RegistryError(Exception):
    pass


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class Registry:
    def __init__(self, data_dir: Path):
        self.root = (data_dir / "registry").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _system_dir(self, system: str) -> Path:
        if not NAME.match(system):
            raise RegistryError("invalid system name")
        path = (self.root / system).resolve()
        if path.parent != self.root:
            raise RegistryError("invalid system name")
        return path

    def publish(
        self,
        system: str,
        repo_url: str,
        source_commit: str,
        candidates: list[Operation],
        tests: dict[str, ContractTestResult],
    ) -> WrapperVersion:
        """Save a new version containing only operations whose contract tests passed.

        Operations that failed, or were tested against another commit, are listed in
        `rejected` and never served (FR-3). Returns the saved version.
        """
        published: list[Operation] = []
        rejected: dict[str, str] = {}
        for op in candidates:
            result = tests.get(op.tool)
            if result is None:
                rejected[op.tool] = "no contract test"
            elif not result.passed or result.cases < 1:
                rejected[op.tool] = "contract test failed"
            elif result.source_commit != source_commit:
                rejected[op.tool] = "tested against a different commit"
            else:
                published.append(op)
        if not published:
            raise RegistryError("no operation passed its contract test; nothing published")

        with self._lock:
            directory = self._system_dir(system)
            version_no = max(self.versions(system), default=0) + 1
            version = WrapperVersion(
                system=system,
                version=version_no,
                source_commit=source_commit,
                repo_url=repo_url,
                operations=published,
                tests={op.tool: tests[op.tool] for op in published},
                rejected=rejected,
            )
            _atomic_write(directory / f"v{version_no}.json", version.model_dump_json(indent=2))
            _atomic_write(directory / "current", str(version_no))
        return version

    def versions(self, system: str) -> list[int]:
        directory = self._system_dir(system)
        if not directory.is_dir():
            return []
        found = []
        for path in directory.glob("v*.json"):
            stem = path.stem[1:]
            if stem.isdigit():
                found.append(int(stem))
        return sorted(found)

    def load(self, system: str, version: int) -> WrapperVersion:
        path = self._system_dir(system) / f"v{int(version)}.json"
        if not path.is_file():
            raise RegistryError(f"{system} has no version {version}")
        # Re-validate on load so a hand-edited file can't publish an untested operation.
        return WrapperVersion.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def current(self, system: str) -> WrapperVersion | None:
        pointer = self._system_dir(system) / "current"
        if not pointer.is_file():
            return None
        text = pointer.read_text(encoding="utf-8").strip()
        if not text.isdigit():
            raise RegistryError(f"corrupt current pointer for {system}")
        return self.load(system, int(text))

    def rollback(self, system: str, version: int) -> WrapperVersion:
        with self._lock:
            loaded = self.load(system, version)
            _atomic_write(self._system_dir(system) / "current", str(loaded.version))
        return loaded

    def systems(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and NAME.match(p.name))

    def live_operations(self) -> dict[str, tuple[Operation, WrapperVersion]]:
        """All published operations across systems, keyed by namespaced tool name."""
        live: dict[str, tuple[Operation, WrapperVersion]] = {}
        for system in self.systems():
            version = self.current(system)
            if version is None:
                continue
            for op in version.operations:
                live[op.tool] = (op, version)
        return live
