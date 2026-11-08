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
  GET  /v1/established                  established systems, listed only, never called (FR-15)
  /mcp                                  MCP over Streamable HTTP (FR-2, FR-5)
  POST /v1/admin/systems                onboard a repo            (admin token)
  POST /v1/admin/systems/{s}/heal       start a repair            (admin token)
  POST /v1/admin/systems/{s}/check      check for code changes    (admin token)
  POST /v1/admin/systems/{s}/rollback   move to an older version  (admin token)
  POST /v1/admin/established            list an established system from its OpenAPI file (admin token)

Security posture:
- Every route except /health needs a bearer token. Gateway tokens read and call;
  admin tokens are separate and are the only ones that can change anything.
  The app refuses to start without a gateway token (fail closed).
- Every tool call goes through Validator.validate_call (PRD section 7), REST and MCP,
  including per-token scopes (REPLIC8_TOKEN_SCOPES). Tool lists show only what a token may call.
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
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field, field_validator

from .config import Settings
from .established import Catalog, EstablishedError, EstablishedImporter, legacy_name_taken
from .events import EventLog
from .executor import Executor
from .graph import build_graph
from .ingest import IngestError
from .sources import canonical_url
from .mcp_server import McpAuth, build_mcp
from .workspaces import Tenant, Tenants, WorkspaceStore
from .models import NAME, Access
from .registry import Registry, RegistryError
from .sandbox import SandboxError
from .validator import Denied, Validator

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
    # Wrap functions, command-line programs, or whatever the repo has.
    mode: Literal["auto", "functions", "programs"] = "auto"

    @field_validator("known_values")
    @classmethod
    def _check_known_values(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        for field, items in value.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", field) or not 1 <= len(items) <= 5:
                raise ValueError("bad known_values")
            if any(not 1 <= len(i) <= 64 or "=" in i or any(ord(c) < 32 for c in i) for i in items):
                raise ValueError("bad known_values")
        return value


class EstablishedRequest(BaseModel):
    system: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    repo_url: str = Field(max_length=300)
    # True for the parent company: its agents use REPLIC8, so the graph draws it into the gateway.
    parent: bool = False
    # Where the OpenAPI file is in the repo, if it isn't found automatically.
    spec_path: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._/-]{1,200}$")


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


class WorkspaceRequest(BaseModel):
    name: str = Field(default="", max_length=60)


def create_app(settings: Settings, registry: Registry, executor: Executor, *,
               pipeline=None, events: EventLog | None = None, catalog: Catalog | None = None,
               workspaces: WorkspaceStore | None = None,
               build_workspace: Callable[[str, Path], Tenant] | None = None) -> FastAPI:
    """Without `workspaces`, there is one shared space (the gateway's configured tokens).
    With `workspaces` and `build_workspace`, workspace tokens open their own spaces too."""
    if not settings.gateway_tokens:
        raise RuntimeError("REPLIC8_GATEWAY_TOKENS is empty; refusing to start an open gateway")
    settings.validate()
    events = events or (pipeline.events if pipeline is not None else EventLog())
    catalog = catalog or Catalog(settings.data_dir)
    default = Tenant(id="default", registry=registry, events=events, validator=Validator(settings, registry),
                     catalog=catalog, importer=EstablishedImporter(settings, catalog, registry, events),
                     pipeline=pipeline)
    tenants = Tenants(default, workspaces, build_workspace)

    def on_failure(t: Tenant, tool: str, exc: SandboxError) -> None:
        if t.pipeline is not None:
            t.pipeline.trigger_heal(tool, exc)
        else:
            t.events.add("call_failed", system=tool.split(".", 1)[0], tool=tool, detail=type(exc).__name__)

    mcp = build_mcp(tenants.for_token, executor, on_failure)
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
                           allow_methods=["GET", "POST", "DELETE"], allow_headers=["Authorization", "Content-Type"])
    bearer = HTTPBearer(auto_error=False)

    def _key(creds: HTTPAuthorizationCredentials | None) -> str:
        return creds.credentials if creds and creds.scheme.lower() == "bearer" else ""

    def reader(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> tuple[Tenant, str]:
        token = _key(creds)
        t = tenants.for_token(token)
        return t, t.validator.authenticate(token)

    def admin(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> tuple[Tenant, str]:
        # In a workspace, its own token is the owner and may run admin actions there.
        token = _key(creds)
        t = tenants.for_token(token)
        return t, t.validator.authenticate(token, admin=True)

    def master(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        """Only the gateway's admin token (never a workspace token) manages workspaces."""
        if not tenants.enabled:
            raise HTTPException(503, "workspaces are not enabled on this gateway")
        token = _key(creds)
        if workspaces.resolve(token) is not None:
            raise HTTPException(403, "use the gateway admin token to manage workspaces")
        return default.validator.authenticate(token, admin=True)

    def need_pipeline(t: Tenant):
        if t.pipeline is None:
            raise HTTPException(503, "pipeline is not configured on this gateway")
        return t.pipeline

    def need_system(t: Tenant, system: str) -> str:
        if not NAME.match(system):
            raise HTTPException(404, "unknown system")
        if t.registry.current(system) is None:
            raise HTTPException(404, "unknown system")
        return system

    @app.exception_handler(Denied)
    async def _denied(request: Request, exc: Denied):
        return JSONResponse({"detail": exc.message}, status_code=exc.status, headers=exc.headers)

    @app.exception_handler(Exception)
    async def _hide_internals(request: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse({"detail": "internal error"}, status_code=500)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/workspaces", status_code=201)
    def create_workspace(body: WorkspaceRequest | None = None, who: str = Depends(master)) -> dict[str, Any]:
        workspace_id, token = workspaces.create((body.name if body else "") or "")
        return {**workspaces.info(workspace_id), "token": token,
                "note": "Save this token: it opens this workspace and can't be shown again."}

    @app.delete("/v1/workspaces/{workspace_id}")
    def delete_workspace(workspace_id: str, who: str = Depends(master)) -> dict[str, Any]:
        try:
            deleted = workspaces.delete(workspace_id)
        except ValueError:
            deleted = False
        if not deleted:
            raise HTTPException(404, "unknown workspace")
        tenants.forget(workspace_id)
        return {"deleted": workspace_id}

    @app.get("/v1/workspace")
    def current_workspace(ctx: tuple[Tenant, str] = Depends(reader)) -> dict[str, Any]:
        t, _ = ctx
        if t.is_workspace:
            return {"kind": "workspace", **workspaces.info(t.id)}
        return {"kind": "default", "workspaces_enabled": tenants.enabled}

    @app.get("/v1/operations")
    def list_operations(ctx: tuple[Tenant, str] = Depends(reader)) -> dict[str, Any]:
        t, who = ctx
        return {"operations": [_operation_view(tool, op, version, settings)
                               for tool, (op, version) in sorted(t.registry.live_operations().items())
                               if t.validator.allowed(who, tool)]}

    @app.post("/v1/operations/{tool}")
    def call_operation(tool: str, body: CallRequest,
                       creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict[str, Any]:
        token = _key(creds)
        t = tenants.for_token(token)
        approved = t.validator.validate_call(token, tool, body.input)
        op, version = approved.op, approved.version
        try:
            result = executor.call(op, version, body.input)
        except SandboxError as exc:
            on_failure(t, tool, exc)
            raise HTTPException(exc.status, str(exc)) from None
        return {"result": result, "provenance": {
            "tool": tool, "tier": op.tier.value, "source": str(op.source),
            "version": version.version, "source_commit": version.source_commit}}

    @app.get("/v1/openapi.json")
    def tools_openapi(ctx: tuple[Tenant, str] = Depends(reader)) -> dict[str, Any]:
        return openapi_for(ctx[0].registry, settings)

    @app.get("/v1/graph")
    def graph(ctx: tuple[Tenant, str] = Depends(reader)) -> dict[str, Any]:
        t = ctx[0]
        return build_graph(t.registry, settings.write_allowlist, t.catalog)

    @app.get("/v1/events")
    def list_events(after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                    ctx: tuple[Tenant, str] = Depends(reader)) -> dict[str, Any]:
        return {"events": ctx[0].events.since(after, limit)}

    @app.get("/v1/systems")
    def systems(ctx: tuple[Tenant, str] = Depends(reader)) -> dict[str, Any]:
        t = ctx[0]
        out = []
        for system in t.registry.systems():
            current = t.registry.current(system)
            if current is not None:
                out.append({**_version_view(current), "versions": t.registry.versions(system)})
        return {"systems": out}

    @app.get("/v1/systems/{system}/versions")
    def versions(system: str, ctx: tuple[Tenant, str] = Depends(reader)) -> dict[str, Any]:
        t = ctx[0]
        need_system(t, system)
        current = t.registry.current(system)
        return {"current": current.version if current else None,
                "versions": [_version_view(t.registry.load(system, v)) for v in t.registry.versions(system)]}

    @app.get("/v1/established")
    def established(ctx: tuple[Tenant, str] = Depends(reader)) -> dict[str, Any]:
        return {"systems": [entry.view() for entry in ctx[0].catalog.all()]}

    @app.post("/v1/admin/established", status_code=202)
    def import_established(body: EstablishedRequest, ctx: tuple[Tenant, str] = Depends(admin)) -> dict[str, Any]:
        t = ctx[0]
        try:
            canonical_url(body.repo_url, settings.local_repo_root)
        except IngestError:
            raise HTTPException(422, "repository URL not accepted (use https://github.com/owner/repo)") from None
        if legacy_name_taken(t.registry, body.system) or (t.pipeline is not None and t.pipeline.busy(body.system)):
            raise HTTPException(409, "that name is already used by a legacy system")
        if t.importer.busy(body.system):
            raise HTTPException(409, "this system is already being processed")

        def work():
            try:
                t.importer.run(body.system, body.repo_url, parent=body.parent, spec_path=body.spec_path)
            except EstablishedError as exc:  # reported through events
                log.info("listing %s failed: %s", body.system, exc)
            except Exception:  # noqa: BLE001
                log.exception("listing %s failed", body.system)
                t.events.add("onboard_failed", system=body.system, detail="internal error")

        threading.Thread(target=work, name=f"established-{body.system}", daemon=True).start()
        return {"status": "started", "system": body.system, "watch": "/v1/events"}

    @app.post("/v1/admin/systems", status_code=202)
    def onboard(body: OnboardRequest, ctx: tuple[Tenant, str] = Depends(admin)) -> dict[str, Any]:
        t = ctx[0]
        p = need_pipeline(t)
        if t.catalog.get(body.system) is not None or t.importer.busy(body.system):
            raise HTTPException(409, "that name is already used by an established system")
        # Refuse bad input now: once the work runs in the background there is nobody to tell.
        try:
            canonical_url(body.repo_url, settings.local_repo_root)
        except IngestError:
            raise HTTPException(422, "repository URL not accepted (use https://github.com/owner/repo)") from None
        if p.busy(body.system):
            raise HTTPException(409, "this system is already being processed")

        def work():
            try:
                p.onboard(body.system, body.repo_url, body.examples, body.known_values, body.mode)
            except Exception as exc:  # noqa: BLE001 - reported through events
                log.info("onboarding %s failed: %s", body.system, type(exc).__name__)

        threading.Thread(target=work, name=f"onboard-{body.system}", daemon=True).start()
        return {"status": "started", "system": body.system, "watch": "/v1/events"}

    @app.post("/v1/admin/systems/{system}/heal", status_code=202)
    def heal(system: str, ctx: tuple[Tenant, str] = Depends(admin)) -> dict[str, Any]:
        t = ctx[0]
        p = need_pipeline(t)
        need_system(t, system)
        threading.Thread(target=p._heal_quietly, args=(system, "manual"), daemon=True).start()
        return {"status": "started", "system": system, "watch": "/v1/events"}

    @app.post("/v1/admin/systems/{system}/check")
    def check(system: str, ctx: tuple[Tenant, str] = Depends(admin)) -> dict[str, Any]:
        t = ctx[0]
        p = need_pipeline(t)
        need_system(t, system)
        return {"system": system, "change_detected": p.check_for_changes(system)}

    @app.post("/v1/admin/systems/{system}/rollback")
    def rollback(system: str, body: RollbackRequest, ctx: tuple[Tenant, str] = Depends(admin)) -> dict[str, Any]:
        t = ctx[0]
        p = need_pipeline(t)
        need_system(t, system)
        try:
            return _version_view(p.rollback(system, body.version))
        except RegistryError:
            raise HTTPException(404, "unknown version") from None

    app.mount("/mcp", McpAuth(mcp_app, tenants.for_token))
    return app
