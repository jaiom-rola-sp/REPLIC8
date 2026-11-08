"""Caller checks shared by every gateway route, REST and MCP (PRD section 7).

`validate_call(api_key, tool_name, args)` must run at the start of every tool call:
401 bad key, 403 write operation (or tool not allowed), 404 not published,
422 bad input, 429 rate limited. Every call is written to the audit log with the
tool and outcome only, never the input or the token.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
from typing import Any

from fastapi import HTTPException

from .config import TOOL_NAME, Settings
from .executor import CallError, validate_input
from .models import Access, Operation, WrapperVersion
from .registry import Registry

audit = logging.getLogger("replic8.audit")


def token_id(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def _matches(supplied: str, tokens: frozenset[str]) -> bool:
    # Compare against every token so timing doesn't reveal which one matched.
    match = False
    for token in tokens:
        match |= hmac.compare_digest(supplied.encode(), token.encode())
    return match


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


class Guard:
    def __init__(self, settings: Settings, registry: Registry):
        self.settings = settings
        self.registry = registry
        self.limiter = RateLimiter(settings.rate_limit_per_minute)

    def authenticate(self, api_key: str | None, *, admin: bool = False) -> str:
        """Return a short id for the caller, or raise 401/403/429."""
        supplied = api_key or ""
        if admin:
            if not self.settings.admin_tokens:
                raise HTTPException(403, "admin API is disabled (no REPLIC8_ADMIN_TOKENS)")
            ok = _matches(supplied, self.settings.admin_tokens)
        else:
            ok = _matches(supplied, self.settings.gateway_tokens | self.settings.admin_tokens)
        if not supplied or not ok:
            raise HTTPException(401, "missing or invalid token", headers={"WWW-Authenticate": "Bearer"})
        who = token_id(supplied)
        if not self.limiter.allow(who):
            raise HTTPException(429, "rate limit exceeded")
        return who

    def validate_call(self, api_key: str | None, tool_name: str, args: Any) -> tuple[Operation, WrapperVersion]:
        who = self.authenticate(api_key)
        if not isinstance(tool_name, str) or not TOOL_NAME.match(tool_name):
            audit.info("call who=%s tool=? outcome=unknown", who)
            raise HTTPException(404, "unknown operation")
        live = self.registry.live_operations().get(tool_name)
        if live is None:
            audit.info("call who=%s tool=%s outcome=unknown", who, tool_name)
            raise HTTPException(404, "unknown operation")
        op, version = live
        if op.access is Access.write and tool_name not in self.settings.write_allowlist:
            audit.warning("call who=%s tool=%s outcome=write_blocked", who, tool_name)
            raise HTTPException(403, "write operations are disabled")
        if not isinstance(args, dict):
            raise HTTPException(422, "input must be a JSON object")
        try:
            validate_input(op, args)
        except CallError as exc:
            audit.info("call who=%s tool=%s outcome=bad_input", who, tool_name)
            raise HTTPException(422, str(exc)) from None
        audit.info("call who=%s tool=%s outcome=allowed", who, tool_name)
        return op, version
