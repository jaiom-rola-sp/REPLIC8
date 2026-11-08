"""MCP server for the gateway (FR-2, FR-5): every published read operation as an MCP tool.

Served over Streamable HTTP at /mcp with the same bearer tokens as REST. Each
tools/call goes through the same validate_call and Executor as REST, so the
write block, schemas, rate limit, audit log and self-heal trigger all apply.
"""

from __future__ import annotations

import contextvars
import json
from typing import Any, Callable

import anyio
import mcp.types as types
from fastapi import HTTPException
from mcp.server.lowlevel import Server

from .executor import Executor
from .models import Access
from .registry import Registry
from .sandbox import SandboxError
from .security import Guard

# The caller's token for this request, set by the auth wrapper below. Never logged.
current_key: contextvars.ContextVar[str] = contextvars.ContextVar("replic8_mcp_key", default="")


def build_mcp(registry: Registry, guard: Guard, executor: Executor,
              on_failure: Callable[[str, SandboxError], Any]) -> Server:
    async def list_tools(ctx, params) -> types.ListToolsResult:
        guard.authenticate(current_key.get())
        tools = []
        for tool, (op, version) in sorted(registry.live_operations().items()):
            if op.access is Access.write and tool not in guard.settings.write_allowlist:
                continue
            tools.append(types.Tool(
                name=tool,
                description=f"{op.description} (source {op.source}, v{version.version}, tier {op.tier.value})",
                input_schema=op.input_schema,
                annotations=types.ToolAnnotations(read_only_hint=op.access is Access.read,
                                                  destructive_hint=False, open_world_hint=False),
            ))
        return types.ListToolsResult(tools=tools)

    async def call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
        args = params.arguments or {}
        try:
            op, version = guard.validate_call(current_key.get(), params.name, args)
        except HTTPException as exc:
            return _error(str(exc.detail))
        try:
            result = await anyio.to_thread.run_sync(executor.call, op, version, args)
        except SandboxError as exc:
            on_failure(params.name, exc)
            return _error(str(exc))
        provenance = {"tool": params.name, "tier": op.tier.value, "source": str(op.source),
                      "version": version.version, "source_commit": version.source_commit}
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps({"result": result, "provenance": provenance}))],
            structured_content={"result": result, "provenance": provenance},
            is_error=False,
        )

    return Server("REPLIC8", version="0.1.0",
                  instructions="Read-only tools generated from legacy systems. Each result includes provenance.",
                  on_list_tools=list_tools, on_call_tool=call_tool)


def _error(message: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=message)], is_error=True)


class McpAuth:
    """ASGI wrapper: require a valid bearer token before any MCP traffic, and pass it to the handlers."""

    def __init__(self, app, guard: Guard):
        self.app = app
        self.guard = guard

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        auth = dict(scope.get("headers", [])).get(b"authorization", b"").decode("latin-1")
        key = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        try:
            self.guard.authenticate(key)
        except HTTPException as exc:
            body = json.dumps({"detail": exc.detail}).encode()
            await send({"type": "http.response.start", "status": exc.status_code,
                        "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
            await send({"type": "http.response.body", "body": body})
            return
        token = current_key.set(key)
        try:
            await self.app(scope, receive, send)
        finally:
            current_key.reset(token)
