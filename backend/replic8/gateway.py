"""One gateway for every published operation (FR-5), read-only by default (FR-13).

Security posture:
- Every route except /health needs a bearer token from REPLIC8_GATEWAY_TOKENS.
  The app refuses to start without one (fail closed).
- Write operations return 403 unless listed in REPLIC8_WRITE_OPS.
- Request bodies are size-capped; input and output are checked against the
  published JSON schemas.
- Errors never echo legacy stderr, stack traces, or caller input.
- Per-token rate limit, and an audit log line per call (tool and outcome only).
- No CORS, and no unauthenticated docs pages.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .config import TOOL_NAME, Settings
from .executor import CallError, Executor
from .models import Access
from .registry import Registry

audit = logging.getLogger("replic8.audit")
MAX_BODY = 64_000


class CallRequest(BaseModel):
    input: dict[str, Any]


class BodyLimit:
    """ASGI middleware: reject bodies over the cap, even without a Content-Length header."""

    def __init__(self, app, limit: int):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        for name, value in scope.get("headers", []):
            if name == b"content-length" and (not value.isdigit() or int(value) > self.limit):
                return await JSONResponse({"detail": "request body too large"}, 413)(scope, receive, send)
        seen = 0

        async def limited_receive():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.limit:
                    raise HTTPException(413, "request body too large")
            return message

        return await self.app(scope, limited_receive, send)


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


def _token_id(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def create_app(settings: Settings, registry: Registry, executor: Executor) -> FastAPI:
    if not settings.gateway_tokens:
        raise RuntimeError("REPLIC8_GATEWAY_TOKENS is empty; refusing to start an open gateway")
    settings.validate()

    app = FastAPI(title="replic8 gateway", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimit, limit=MAX_BODY)
    bearer = HTTPBearer(auto_error=False)
    limiter = RateLimiter(settings.rate_limit_per_minute)

    def caller(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        supplied = creds.credentials if creds and creds.scheme.lower() == "bearer" else ""
        # Compare against every token so timing doesn't reveal which one matched.
        match = False
        for token in settings.gateway_tokens:
            match |= hmac.compare_digest(supplied.encode(), token.encode())
        if not match:
            raise HTTPException(401, "missing or invalid token", headers={"WWW-Authenticate": "Bearer"})
        who = _token_id(supplied)
        if not limiter.allow(who):
            raise HTTPException(429, "rate limit exceeded")
        return who

    @app.exception_handler(Exception)
    async def _hide_internals(request: Request, exc: Exception):
        logging.getLogger("replic8.gateway").exception("unhandled error")
        return JSONResponse({"detail": "internal error"}, status_code=500)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/operations")
    def list_operations(who: str = Depends(caller)) -> dict[str, Any]:
        ops = []
        for tool, (op, version) in sorted(registry.live_operations().items()):
            ops.append({
                "tool": tool,
                "description": op.description,
                "tier": op.tier.value,
                "access": op.access.value,
                "enabled": op.access is Access.read or tool in settings.write_allowlist,
                "source": str(op.source),
                "version": version.version,
                "source_commit": version.source_commit,
                "input_schema": op.input_schema,
                "output_schema": op.output_schema,
            })
        return {"operations": ops}

    @app.post("/v1/operations/{tool}")
    def call_operation(tool: str, body: CallRequest, who: str = Depends(caller)) -> dict[str, Any]:
        if not TOOL_NAME.match(tool):
            raise HTTPException(404, "unknown operation")
        live = registry.live_operations().get(tool)
        if live is None:
            audit.info("call who=%s tool=%s outcome=unknown", who, tool)
            raise HTTPException(404, "unknown operation")
        op, version = live
        if op.access is Access.write and tool not in settings.write_allowlist:
            audit.warning("call who=%s tool=%s outcome=write_blocked", who, tool)
            raise HTTPException(403, "write operations are disabled")
        try:
            result = executor.call(op, version, body.input)
        except CallError as exc:
            audit.info("call who=%s tool=%s outcome=error status=%s", who, tool, exc.status)
            raise HTTPException(exc.status, str(exc)) from None
        audit.info("call who=%s tool=%s outcome=ok", who, tool)
        return {
            "result": result,
            "provenance": {
                "tool": tool,
                "tier": op.tier.value,
                "source": str(op.source),
                "version": version.version,
                "source_commit": version.source_commit,
            },
        }

    return app
