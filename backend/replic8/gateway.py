"""One gateway for every published operation (FR-5), read-only by default (FR-13).

Routes
  GET  /health                          open, no data
  GET  /v1/operations                   registry (the dashboard reads this)
  POST /v1/operations/{tool}            call a tool
  GET  /v1/openapi.json                 OpenAPI for the published tools (FR-2)
  GET  /v1/graph                        systems, operations, schema data links (FR-6)
  GET  /v1/events?after=N               activity log
  GET  /v1/systems                      systems with their current version
  GET  /v1/systems/{system}/versions    version history (FR-8)
  /mcp                                  MCP over Streamable HTTP (FR-2, FR-5)
  POST /v1/admin/systems                onboard a repo            (admin token)
  POST /v1/admin/systems/{s}/heal       start a repair            (admin token)
  POST /v1/admin/systems/{s}/check      check for code changes    (admin token)
  POST /v1/admin/systems/{s}/rollback   move to an older version  (admin token)

Security posture:
- Every route except /health needs a bearer token. Gateway tokens read and call;
  admin tokens are separate and are the only ones that can change anything.
  The app refuses to start without a gateway token (fail closed).
- Every tool call goes through Guard.validate_call (PRD section 7), REST and MCP.
- Write operations return 403 unless listed in REPLIC8_WRITE_OPS.
- Request bodies are size-capped; input and output are checked against schemas.
- Errors never echo legacy stderr, stack traces, or caller input.
- No CORS unless REPLIC8_CORS_ORIGINS lists exact origins; no unauthenticated docs.
"""

from __future__ import annotations

import contextlib
import logging
import re
import threading
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field, field_validator

from .config import Settings
from .events import EventLog
from .executor import Executor
from .graph import build_graph
from .ingest import IngestError
from .sources import canonical_url
from .mcp_server import McpAuth, build_mcp
from .models import NAME, Access
from .registry import Registry, RegistryError
from .sandbox import SandboxError
from .security import Guard

log = logging.getLogger("replic8.gateway")
MAX_BODY = 64_000


class CallRequest(BaseModel):
    input: dict[str, Any]


class OnboardRequest(BaseModel):
    system: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    repo_url: str = Field(max_length=300)
    # Optional operator-supplied example inputs per operation name, for contract tests.
    examples: dict[str, list[dict[str, Any]]] = Field(default_factory=dict, max_length=20)
    # Known-good values by input field name, e.g. {"request_id": ["R-1001"]}. They become contract-test
    # inputs that hit real records. Limits match what the call shim accepts.
    known_values: dict[str, list[str]] = Field(default_factory=dict, max_length=20)

    @field_validator("known_values")
    @classmethod
    def _check_known_values(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        for field, items in value.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", field) or not 1 <= len(items) <= 5:
                raise ValueError("bad known_values")
            if any(not 1 <= len(i) <= 64 or "=" in i or any(ord(c) < 32 for c in i) for i in items):
                raise ValueError("bad known_values")
        return value


class RollbackRequest(BaseModel):
    version: int = Field(ge=1)


class McpSlash:
    """Let clients use /mcp as well as /mcp/ without a redirect."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            scope = {**scope, "path": "/mcp/", "raw_path": b"/mcp/"}
        return await self.app(scope, receive, send)


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


def _operation_view(tool: str, op, version, settings: Settings) -> dict[str, Any]:
    return {
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
        "contract_cases": version.tests[tool].cases if tool in version.tests else 0,
    }


def _version_view(v) -> dict[str, Any]:
    return {
        "system": v.system, "version": v.version, "source_commit": v.source_commit, "repo": v.repo_url,
        "created_at": v.created_at.isoformat(), "reason": v.reason, "parent_version": v.parent_version,
        "operations": [op.tool for op in v.operations],
        "rejected": v.rejected,
        "tests": {tool: {"passed": t.passed, "cases": t.cases} for tool, t in v.tests.items()},
    }


def openapi_for(registry: Registry, settings: Settings) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for tool, (op, version) in sorted(registry.live_operations().items()):
        if op.access is Access.write and tool not in settings.write_allowlist:
            continue
        paths[f"/v1/operations/{tool}"] = {"post": {
            "operationId": tool.replace(".", "__"),
            "summary": op.description,
            "description": f"Source {op.source} at {version.source_commit[:12]} (v{version.version}, tier {op.tier.value}).",
            "security": [{"bearer": []}],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "type": "object", "required": ["input"], "properties": {"input": op.input_schema}}}}},
            "responses": {
                "200": {"description": "Result with provenance", "content": {"application/json": {"schema": {
                    "type": "object", "properties": {"result": op.output_schema, "provenance": {"type": "object"}}}}}},
                "401": {"description": "Missing or invalid token"},
                "403": {"description": "Write operation disabled"},
                "422": {"description": "Input does not match the schema"},
                "502": {"description": "Legacy system error"},
                "504": {"description": "Legacy system timed out"},
            },
        }}
    return {"openapi": "3.1.0", "info": {"title": "REPLIC8 gateway", "version": "0.1.0"},
            "components": {"securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}}},
            "paths": paths}


def create_app(settings: Settings, registry: Registry, executor: Executor, *,
               pipeline=None, events: EventLog | None = None) -> FastAPI:
    if not settings.gateway_tokens:
        raise RuntimeError("REPLIC8_GATEWAY_TOKENS is empty; refusing to start an open gateway")
    settings.validate()
    guard = Guard(settings, registry)
    events = events or (pipeline.events if pipeline is not None else EventLog())

    def on_failure(tool: str, exc: SandboxError) -> None:
        if pipeline is not None:
            pipeline.trigger_heal(tool, exc)
        else:
            events.add("call_failed", system=tool.split(".", 1)[0], tool=tool, detail=type(exc).__name__)

    mcp = build_mcp(registry, guard, executor, on_failure)
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/", stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=list(settings.allowed_hosts),
            allowed_origins=list(settings.cors_origins)),
    )

    @contextlib.asynccontextmanager
    async def lifespan(app):
        stop = threading.Event()
        if pipeline is not None and settings.poll_interval_s:
            threading.Thread(target=pipeline.poll_forever, args=(settings.poll_interval_s, stop),
                             name="change-poll", daemon=True).start()
        async with mcp.session_manager.run():
            yield
        stop.set()

    app = FastAPI(title="REPLIC8 gateway", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(BodyLimit, limit=MAX_BODY)
    app.add_middleware(McpSlash)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
                           allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])
    bearer = HTTPBearer(auto_error=False)

    def _key(creds: HTTPAuthorizationCredentials | None) -> str:
        return creds.credentials if creds and creds.scheme.lower() == "bearer" else ""

    def reader(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        return guard.authenticate(_key(creds))

    def admin(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        return guard.authenticate(_key(creds), admin=True)

    def need_pipeline():
        if pipeline is None:
            raise HTTPException(503, "pipeline is not configured on this gateway")
        return pipeline

    def need_system(system: str) -> str:
        if not NAME.match(system):
            raise HTTPException(404, "unknown system")
        if registry.current(system) is None:
            raise HTTPException(404, "unknown system")
        return system

    @app.exception_handler(Exception)
    async def _hide_internals(request: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse({"detail": "internal error"}, status_code=500)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/operations")
    def list_operations(who: str = Depends(reader)) -> dict[str, Any]:
        return {"operations": [_operation_view(tool, op, version, settings)
                               for tool, (op, version) in sorted(registry.live_operations().items())]}

    @app.post("/v1/operations/{tool}")
    def call_operation(tool: str, body: CallRequest,
                       creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict[str, Any]:
        op, version = guard.validate_call(_key(creds), tool, body.input)
        try:
            result = executor.call(op, version, body.input)
        except SandboxError as exc:
            on_failure(tool, exc)
            raise HTTPException(exc.status, str(exc)) from None
        return {"result": result, "provenance": {
            "tool": tool, "tier": op.tier.value, "source": str(op.source),
            "version": version.version, "source_commit": version.source_commit}}

    @app.get("/v1/openapi.json")
    def tools_openapi(who: str = Depends(reader)) -> dict[str, Any]:
        return openapi_for(registry, settings)

    @app.get("/v1/graph")
    def graph(who: str = Depends(reader)) -> dict[str, Any]:
        return build_graph(registry, settings.write_allowlist)

    @app.get("/v1/events")
    def list_events(after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                    who: str = Depends(reader)) -> dict[str, Any]:
        return {"events": events.since(after, limit)}

    @app.get("/v1/systems")
    def systems(who: str = Depends(reader)) -> dict[str, Any]:
        out = []
        for system in registry.systems():
            current = registry.current(system)
            if current is not None:
                out.append({**_version_view(current), "versions": registry.versions(system)})
        return {"systems": out}

    @app.get("/v1/systems/{system}/versions")
    def versions(system: str, who: str = Depends(reader)) -> dict[str, Any]:
        need_system(system)
        current = registry.current(system)
        return {"current": current.version if current else None,
                "versions": [_version_view(registry.load(system, v)) for v in registry.versions(system)]}

    @app.post("/v1/admin/systems", status_code=202)
    def onboard(body: OnboardRequest, who: str = Depends(admin)) -> dict[str, Any]:
        p = need_pipeline()
        # Refuse bad input now: once the work runs in the background there is nobody to tell.
        try:
            canonical_url(body.repo_url, settings.local_repo_root)
        except IngestError:
            raise HTTPException(422, "repository URL not accepted (use https://github.com/owner/repo)") from None
        if p.busy(body.system):
            raise HTTPException(409, "this system is already being processed")

        def work():
            try:
                p.onboard(body.system, body.repo_url, body.examples, body.known_values)
            except Exception as exc:  # noqa: BLE001 - reported through events
                log.info("onboarding %s failed: %s", body.system, type(exc).__name__)

        threading.Thread(target=work, name=f"onboard-{body.system}", daemon=True).start()
        return {"status": "started", "system": body.system, "watch": "/v1/events"}

    @app.post("/v1/admin/systems/{system}/heal", status_code=202)
    def heal(system: str, who: str = Depends(admin)) -> dict[str, Any]:
        p = need_pipeline()
        need_system(system)
        threading.Thread(target=p._heal_quietly, args=(system, "manual"), daemon=True).start()
        return {"status": "started", "system": system, "watch": "/v1/events"}

    @app.post("/v1/admin/systems/{system}/check")
    def check(system: str, who: str = Depends(admin)) -> dict[str, Any]:
        p = need_pipeline()
        need_system(system)
        return {"system": system, "change_detected": p.check_for_changes(system)}

    @app.post("/v1/admin/systems/{system}/rollback")
    def rollback(system: str, body: RollbackRequest, who: str = Depends(admin)) -> dict[str, Any]:
        p = need_pipeline()
        need_system(system)
        try:
            return _version_view(p.rollback(system, body.version))
        except RegistryError:
            raise HTTPException(404, "unknown version") from None

    app.mount("/mcp", McpAuth(mcp_app, guard))
    return app
