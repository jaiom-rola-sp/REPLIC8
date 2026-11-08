"""Workspaces: separate, token-opened spaces on one gateway.

Someone with the master admin token creates a workspace and gets one workspace
token back, shown once. That token opens the workspace: everything imported,
called, repaired or rolled back in it is saved under its own folder, and only
that token can see or change it (REST and MCP). Without it, the dashboard shows
a blank workspace; with it, the work comes back.

- Only a SHA-256 of each token is stored, never the token.
- A workspace token is its workspace's owner: it can read, call tools and run
  admin actions (import, check, repair, roll back) inside that workspace only.
- Each workspace has its own registry, event log and established catalog under
  <data_dir>/workspaces/<id>/. Repo clones and builds stay shared: they are keyed
  by repo and commit and never served by the API.
- The gateway's configured tokens keep using the original (default) data, so
  nothing changes for existing setups.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .validator import Denied, Validator

WORKSPACE_ID = re.compile(r"^[0-9a-f]{12}$")
TOKEN_PREFIX = "r8w_"
NAME_TEXT = re.compile(r"[^A-Za-z0-9 ._-]")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class WorkspaceStore:
    """Creates workspaces and maps a workspace token to its workspace id."""

    def __init__(self, data_dir: Path):
        self.root = (data_dir / "workspaces").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._by_hash: dict[str, str] = {}
        for meta in self.root.glob("*/workspace.json"):
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if WORKSPACE_ID.match(str(data.get("id", ""))) and isinstance(data.get("token_sha256"), str):
                self._by_hash[data["token_sha256"]] = data["id"]

    def dir(self, workspace_id: str) -> Path:
        if not WORKSPACE_ID.match(workspace_id):
            raise ValueError("invalid workspace id")
        return self.root / workspace_id

    def create(self, name: str = "") -> tuple[str, str]:
        """Make an empty workspace. Returns (id, token); the token is not stored and can't be shown again."""
        with self._lock:
            workspace_id = secrets.token_hex(6)
            token = TOKEN_PREFIX + secrets.token_urlsafe(32)
            folder = self.dir(workspace_id)
            folder.mkdir(parents=True, exist_ok=False)
            meta = {"id": workspace_id, "name": NAME_TEXT.sub("", name)[:60],
                    "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "token_sha256": _hash(token)}
            (folder / "workspace.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            self._by_hash[meta["token_sha256"]] = workspace_id
            return workspace_id, token

    def resolve(self, token: str | None) -> str | None:
        """The workspace this token opens, or None. Hash lookup, so timing reveals nothing useful."""
        if not token or not token.startswith(TOKEN_PREFIX) or len(token) > 200:
            return None
        return self._by_hash.get(_hash(token))

    def info(self, workspace_id: str) -> dict[str, Any]:
        data = json.loads((self.dir(workspace_id) / "workspace.json").read_text(encoding="utf-8"))
        return {"id": data["id"], "name": data.get("name", ""), "created_at": data.get("created_at")}

    def all(self) -> list[dict[str, Any]]:
        return sorted((self.info(wid) for wid in set(self._by_hash.values())), key=lambda w: w["created_at"] or "")

    def delete(self, workspace_id: str) -> bool:
        with self._lock:
            folder = self.dir(workspace_id)
            if not folder.is_dir():
                return False
            self._by_hash = {h: w for h, w in self._by_hash.items() if w != workspace_id}
            shutil.rmtree(folder)
            return True


class WorkspaceValidator(Validator):
    """The same checks as Validator.validate_call, but only this workspace's token is accepted,
    and it may use every tool in the workspace (it owns it)."""

    def __init__(self, settings, registry, workspace_id: str, store: WorkspaceStore):
        super().__init__(settings, registry)
        self.workspace_id = workspace_id
        self.store = store

    def authenticate(self, token: str | None, *, admin: bool = False) -> str:
        if self.store.resolve(token) != self.workspace_id:
            raise Denied(401, "missing or invalid token", headers={"WWW-Authenticate": "Bearer"})
        who = f"ws-{self.workspace_id}"
        if not self.limiter.allow(who):
            raise Denied(429, "rate limit exceeded")
        return who

    def is_admin(self, who: str) -> bool:
        return who == f"ws-{self.workspace_id}"

    def allowed(self, who: str, tool: str) -> bool:
        return self.is_admin(who)


@dataclass
class Tenant:
    """Everything one workspace (or the default space) needs to serve requests."""

    id: str
    registry: Any
    events: Any
    validator: Validator
    catalog: Any
    importer: Any
    pipeline: Any = None
    is_workspace: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class Tenants:
    """Picks the tenant for a token: its workspace if it is a workspace token, else the default."""

    def __init__(self, default: Tenant, store: WorkspaceStore | None = None,
                 build: Callable[[str, Path], Tenant] | None = None):
        self.default = default
        self.store = store
        self._build = build
        self._cache: dict[str, Tenant] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.store is not None and self._build is not None

    def for_token(self, token: str | None) -> Tenant:
        if not self.enabled:
            return self.default
        workspace_id = self.store.resolve(token)
        if workspace_id is None:
            return self.default
        with self._lock:
            tenant = self._cache.get(workspace_id)
            if tenant is None:
                tenant = self._build(workspace_id, self.store.dir(workspace_id))
                self._cache[workspace_id] = tenant
            return tenant

    def forget(self, workspace_id: str) -> None:
        with self._lock:
            self._cache.pop(workspace_id, None)
