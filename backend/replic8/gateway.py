"""One gateway for every published operation (FR-5), read-only by default (FR-13).

Security posture:
- Every route except /health goes through `Validator.validate_call` (validator.py):
  bearer token, rate limit, per-token scopes, published tool, write blocking,
  input size and schema. The app refuses to start without a token (fail closed).
- Request bodies are also size-capped before parsing (BodyLimit); output is
  checked against the published schema by the executor.
- Errors never echo legacy stderr, stack traces, or caller input.
- An audit log line per call (token id, tool and outcome only).
- No CORS, and no unauthenticated docs pages.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .config import Settings
from .executor import CallError, Executor
from .models import Access
from .registry import Registry
from .validator import MAX_ARGS_BYTES, Denied, Validator

audit = logging.getLogger("replic8.audit")
MAX_BODY = MAX_ARGS_BYTES


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


def create_app(settings: Settings, registry: Registry, executor: Executor) -> FastAPI:
    validator = Validator(settings, registry)  # refuses to start without tokens

    app = FastAPI(title="replic8 gateway", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimit, limit=MAX_BODY)
    bearer = HTTPBearer(auto_error=False)

    def bearer_token(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        return creds.credentials if creds and creds.scheme.lower() == "bearer" else ""

    def check(token: str, tool: str | None, args: Any):
        try:
            return validator.validate_call(token, tool, args)
        except Denied as exc:
            raise HTTPException(exc.status, exc.message, headers=exc.headers) from None

    @app.exception_handler(Exception)
    async def _hide_internals(request: Request, exc: Exception):
        logging.getLogger("replic8.gateway").exception("unhandled error")
        return JSONResponse({"detail": "internal error"}, status_code=500)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/operations")
    def list_operations(token: str = Depends(bearer_token)) -> dict[str, Any]:
        who = check(token, None, None).who
        ops = []
        for tool, (op, version) in sorted(registry.live_operations().items()):
            if not validator.allowed(who, tool):
                continue
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
    def call_operation(tool: str, body: CallRequest, token: str = Depends(bearer_token)) -> dict[str, Any]:
        approved = check(token, tool, body.input)
        who, op, version = approved.who, approved.op, approved.version
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
