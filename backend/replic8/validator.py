"""One check for every call into REPLIC8 (FR-5, FR-13; PRD section 7).

Every tool call goes through `Validator.validate_call`, from REST and from the MCP
server, so both front doors enforce exactly the same rules:
- a valid bearer token, compared in constant time against every configured token,
- a per-token rate limit,
- a per-token scope allowlist (`maintenance.*` or one tool); no scope means no access
  (admin tokens are unscoped, and are the only tokens the admin routes accept).
  REPLIC8_TOKEN_SCOPES is the starting set; admins can grant or remove scopes at
  runtime (`grant_scope`, `remove_scope`), in memory only. A runtime grant never
  covers a write operation: only REPLIC8_TOKEN_SCOPES can,
- the tool must be published, and write operations stay blocked unless allowlisted,
- input is capped at 64 KB and checked against the published JSON schema.

Denials raise `Denied` with a generic message: no stack traces, legacy stderr or
caller input. The audit log records who (token id), the tool and the outcome only.
This module has no web framework imports, so any transport can reuse it.
"""

from __future__ import annotations

import hmac
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from .config import SCOPE, TOKEN_ID, TOOL_NAME, Settings, token_id
from .executor import CallError, validate_input
from .models import Access, Operation, WrapperVersion
from .registry import Registry

audit = logging.getLogger("replic8.audit")
MAX_ARGS_BYTES = 64_000


class Denied(Exception):
    """A refused call. `status` is an HTTP status code; `message` is safe to show."""

    def __init__(self, status: int, message: str, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.headers = headers


@dataclass(frozen=True)
class Approved:
    who: str  # token id, never the token
    op: Operation | None = None
    version: WrapperVersion | None = None


class RateLimiter:
    def __init__(self, per_minute: int):
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens < 1:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1, now)
            return True


class Validator:
    def __init__(self, settings: Settings, registry: Registry):
        if not settings.gateway_tokens:
            raise RuntimeError("REPLIC8_GATEWAY_TOKENS is empty; refusing to start an open gateway")
        settings.validate()
        self.settings = settings
        self.registry = registry
        self.limiter = RateLimiter(settings.rate_limit_per_minute)
        self._admin_ids = frozenset(token_id(t) for t in settings.admin_tokens)
        self._gateway_ids = frozenset(token_id(t) for t in settings.gateway_tokens)
        # Runtime changes from the admin API: (granted, removed) per token id, on top of
        # REPLIC8_TOKEN_SCOPES. Replaced as a whole under the lock, so readers never see
        # half a change. Not saved: a restart goes back to the configured scopes.
        self._overrides: tuple[dict[str, frozenset[str]], dict[str, frozenset[str]]] = ({}, {})
        self._scope_lock = threading.Lock()

    def is_admin(self, who: str) -> bool:
        return who in self._admin_ids

    def _configured(self, who: str, removed: dict[str, frozenset[str]]) -> frozenset[str]:
        return self.settings.token_scopes.get(who, frozenset()) - removed.get(who, frozenset())

    def scopes(self, who: str) -> frozenset[str]:
        """The token's current scopes: configured, minus removed, plus granted."""
        granted, removed = self._overrides
        return self._configured(who, removed) | granted.get(who, frozenset())

    def allowed(self, who: str, tool: str, *, write: bool = False) -> bool:
        """True if token id `who` may call `tool`. Unknown tokens and empty scopes get nothing.

        Pass write=True for a write operation: only configured scopes count then, so a
        scope granted at runtime can never open a write.
        """
        if self.is_admin(who):
            return True
        granted, removed = self._overrides
        scopes = self._configured(who, removed)
        if not write:
            scopes = scopes | granted.get(who, frozenset())
        return tool in scopes or f"{tool.partition('.')[0]}.*" in scopes

    def _check_scope_change(self, target: Any, scope: Any) -> None:
        if not isinstance(target, str) or not TOKEN_ID.match(target):
            raise Denied(422, "token_id must be 12 lowercase hex characters (see the audit log)")
        if not isinstance(scope, str) or not SCOPE.match(scope):
            raise Denied(422, "scope must be ns.* or ns.tool")
        if target in self._admin_ids:
            raise Denied(422, "admin tokens are unscoped; their scopes can't be changed")
        if target not in self._gateway_ids:
            raise Denied(404, "unknown token id")

    def grant_scope(self, admin: str, target: str, scope: str) -> tuple[frozenset[str], bool]:
        """Give gateway token `target` a scope now. Returns (its scopes, whether anything changed)."""
        self._check_scope_change(target, scope)
        if not scope.endswith(".*"):
            live = self.registry.live_operations().get(scope)
            if scope in self.settings.write_allowlist or (live is not None and live[0].access is Access.write):
                audit.warning("scope_grant_refused admin=%s token=%s scope=%s reason=write", admin, target, scope)
                raise Denied(422, "write operations can't be granted")
        with self._scope_lock:
            before = self.scopes(target)
            granted, removed = self._overrides
            removed = {**removed, target: removed.get(target, frozenset()) - {scope}}
            if scope not in self.settings.token_scopes.get(target, frozenset()):
                granted = {**granted, target: granted.get(target, frozenset()) | {scope}}
            self._overrides = (granted, removed)
            after = self.scopes(target)
        audit.warning("scope_grant admin=%s token=%s scope=%s changed=%s", admin, target, scope, after != before)
        return after, after != before

    def remove_scope(self, admin: str, target: str, scope: str) -> tuple[frozenset[str], bool]:
        """Take a scope away from gateway token `target` now, whether it was configured or granted.

        Removes exactly that entry: removing `ns.*` leaves a separate `ns.tool` in place.
        """
        self._check_scope_change(target, scope)
        with self._scope_lock:
            before = self.scopes(target)
            granted, removed = self._overrides
            granted = {**granted, target: granted.get(target, frozenset()) - {scope}}
            if scope in self.settings.token_scopes.get(target, frozenset()):
                removed = {**removed, target: removed.get(target, frozenset()) | {scope}}
            self._overrides = (granted, removed)
            after = self.scopes(target)
        audit.warning("scope_remove admin=%s token=%s scope=%s changed=%s", admin, target, scope, after != before)
        return after, after != before

    def authenticate(self, token: str | None, *, admin: bool = False) -> str:
        """Return the caller's token id, or raise Denied (401, 403 admin API off, 429).

        admin=True accepts only admin tokens; otherwise gateway and admin tokens both work.
        """
        token = token or ""
        if admin and not self.settings.admin_tokens:
            raise Denied(403, "admin API is disabled (no REPLIC8_ADMIN_TOKENS)")
        known_tokens = self.settings.admin_tokens if admin else \
            self.settings.gateway_tokens | self.settings.admin_tokens
        # Compare against every token so timing doesn't reveal which one matched.
        match = False
        for known in known_tokens:
            match |= hmac.compare_digest(token.encode(), known.encode())
        if not token or not match:
            raise Denied(401, "missing or invalid token", headers={"WWW-Authenticate": "Bearer"})
        who = token_id(token)
        if not self.limiter.allow(who):
            raise Denied(429, "rate limit exceeded")
        return who

    def validate_call(self, token: str, tool_name: str | None, args: Any) -> Approved:
        """Check one call. Pass tool_name=None to only authenticate (e.g. listing tools).

        Returns who is calling and the published operation; raises Denied otherwise.
        """
        who = self.authenticate(token)
        if tool_name is None:
            return Approved(who)

        if not TOOL_NAME.match(tool_name):
            raise Denied(404, "unknown operation")
        if not self.allowed(who, tool_name):
            audit.warning("call who=%s tool=%s outcome=scope_blocked", who, tool_name)
            raise Denied(403, "operation not allowed for this token")
        live = self.registry.live_operations().get(tool_name)
        if live is None:
            audit.info("call who=%s tool=%s outcome=unknown", who, tool_name)
            raise Denied(404, "unknown operation")
        op, version = live
        if op.access is Access.write and tool_name not in self.settings.write_allowlist:
            audit.warning("call who=%s tool=%s outcome=write_blocked", who, tool_name)
            raise Denied(403, "write operations are disabled")
        if op.access is Access.write and not self.allowed(who, tool_name, write=True):
            audit.warning("call who=%s tool=%s outcome=scope_blocked", who, tool_name)
            raise Denied(403, "operation not allowed for this token")

        try:
            size = len(json.dumps(args, separators=(",", ":")).encode("utf-8"))
        except (TypeError, ValueError):
            raise Denied(422, "input must be JSON") from None
        if size > MAX_ARGS_BYTES:
            audit.info("call who=%s tool=%s outcome=too_large", who, tool_name)
            raise Denied(413, "request body too large")
        try:
            validate_input(op, args)
        except CallError as exc:
            audit.info("call who=%s tool=%s outcome=error status=%s", who, tool_name, exc.status)
            raise Denied(exc.status, str(exc)) from None
        audit.info("call who=%s tool=%s outcome=allowed", who, tool_name)
        return Approved(who, op, version)
