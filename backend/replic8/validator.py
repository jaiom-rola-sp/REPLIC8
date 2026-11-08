"""One check for every call into REPLIC8 (FR-5, FR-13; PRD section 7).

Every tool call goes through `Validator.validate_call`, from REST and from the MCP
server, so both front doors enforce exactly the same rules:
- a valid bearer token, compared in constant time against every configured token,
- a per-token rate limit,
- a per-token scope allowlist (`maintenance.*` or one tool); no scope means no access
  (admin tokens are unscoped, and are the only tokens the admin routes accept),
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

from .config import TOOL_NAME, Settings, token_id
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

    def is_admin(self, who: str) -> bool:
        return who in self._admin_ids

    def allowed(self, who: str, tool: str) -> bool:
        """True if token id `who` may call `tool`. Unknown tokens and empty scopes get nothing."""
        if self.is_admin(who):
            return True
        scopes = self.settings.token_scopes.get(who, frozenset())
        namespace = tool.partition(".")[0]
        return tool in scopes or f"{namespace}.*" in scopes

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
