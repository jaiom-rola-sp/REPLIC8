"""Settings read from environment variables. Secrets never live in the repo (NFR Security)."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

MIN_TOKEN_LENGTH = 32
TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}\.[a-z][a-z0-9_]{0,63}$")
# A sandbox image must be pinned by digest (name[:tag]@sha256:<64 hex>). A tag alone can be
# moved to point at a different image; a digest can't.
PINNED_IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,127}(:[A-Za-z0-9._-]{1,128})?@sha256:[0-9a-f]{64}$")
# A scope is a whole namespace (`maintenance.*`) or one tool (`maintenance.get_request`).
SCOPE = re.compile(r"^[a-z][a-z0-9_]{0,31}\.(\*|[a-z][a-z0-9_]{0,63})$")
TOKEN_ID = re.compile(r"^[0-9a-f]{12}$")


def token_id(token: str) -> str:
    """Short, non-secret ID for a token. Used in audit logs and REPLIC8_TOKEN_SCOPES."""
    return hashlib.sha256(token.encode()).hexdigest()[:12]


class ConfigError(ValueError):
    pass


def _csv(name: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


def _scopes(name: str) -> dict[str, frozenset[str]]:
    """Parse `id=ns.*|ns.tool,id2=ns2.*` into {id: {scopes}}."""
    out: dict[str, frozenset[str]] = {}
    for entry in _csv(name):
        tid, _, scopes = entry.partition("=")
        out[tid.strip()] = frozenset(s.strip() for s in scopes.split("|") if s.strip())
    return out


@dataclass(frozen=True)
class SandboxLimits:
    timeout_s: float = 10.0
    memory: str = "256m"
    cpus: str = "0.5"
    pids: int = 64
    max_output_bytes: int = 1_000_000
    max_input_bytes: int = 64_000


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    gateway_tokens: frozenset[str] = frozenset()
    # Admin tokens can onboard repos, trigger repairs and roll back. Keep them
    # separate from the agent/dashboard tokens above.
    admin_tokens: frozenset[str] = frozenset()
    # Which tools each gateway token may call, keyed by token_id(token). A gateway
    # token with no entry can call nothing (fail closed). Admin tokens are unscoped.
    token_scopes: dict[str, frozenset[str]] = field(default_factory=dict)
    # Write operations stay disabled unless named here (FR-13). Empty in v1.
    write_allowlist: frozenset[str] = frozenset()
    # Docker images the sandbox may run. Each must be pinned by digest (see PINNED_IMAGE).
    sandbox_images: frozenset[str] = frozenset()
    sandbox: SandboxLimits = field(default_factory=SandboxLimits)
    max_repo_bytes: int = 200 * 1024 * 1024
    max_repo_files: int = 20_000
    clone_timeout_s: float = 120.0
    rate_limit_per_minute: int = 120
    # Dev/demo only: allow local://<name> repos from this folder. Off when unset.
    local_repo_root: Path | None = None
    # Browser origins allowed to call the gateway directly (exact matches). Empty = no CORS.
    cors_origins: tuple[str, ...] = ()
    # Seconds between checks for legacy code changes (0 = off).
    poll_interval_s: float = 0.0
    # Host headers the MCP endpoint accepts (DNS-rebinding protection), e.g. "replic8.example.com".
    allowed_hosts: tuple[str, ...] = ("127.0.0.1:*", "localhost:*")

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            data_dir=Path(os.environ.get("REPLIC8_DATA_DIR", "./data")).resolve(),
            gateway_tokens=frozenset(_csv("REPLIC8_GATEWAY_TOKENS")),
            admin_tokens=frozenset(_csv("REPLIC8_ADMIN_TOKENS")),
            token_scopes=_scopes("REPLIC8_TOKEN_SCOPES"),
            write_allowlist=frozenset(_csv("REPLIC8_WRITE_OPS")),
            sandbox_images=frozenset(_csv("REPLIC8_SANDBOX_IMAGES")),
            local_repo_root=Path(os.environ["REPLIC8_LOCAL_REPO_ROOT"]).resolve()
            if os.environ.get("REPLIC8_LOCAL_REPO_ROOT") else None,
            cors_origins=tuple(_csv("REPLIC8_CORS_ORIGINS")),
            poll_interval_s=float(os.environ.get("REPLIC8_POLL_SECONDS", "0") or 0),
            allowed_hosts=tuple(_csv("REPLIC8_ALLOWED_HOSTS")) or ("127.0.0.1:*", "localhost:*"),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        for token in self.gateway_tokens | self.admin_tokens:
            if len(token) < MIN_TOKEN_LENGTH:
                raise ConfigError(f"gateway and admin tokens must be at least {MIN_TOKEN_LENGTH} characters")
        if self.gateway_tokens & self.admin_tokens:
            raise ConfigError("admin tokens must differ from gateway tokens")
        known = {token_id(t) for t in self.gateway_tokens}
        for tid, scopes in self.token_scopes.items():
            if not TOKEN_ID.match(tid) or tid not in known:
                raise ConfigError(f"REPLIC8_TOKEN_SCOPES names an unknown token id: {tid!r}")
            for scope in scopes:
                if not SCOPE.match(scope):
                    raise ConfigError(f"invalid scope in REPLIC8_TOKEN_SCOPES (use ns.* or ns.tool): {scope!r}")
        for image in self.sandbox_images:
            if not PINNED_IMAGE.match(image):
                raise ConfigError(f"REPLIC8_SANDBOX_IMAGES must be pinned by digest (name@sha256:...): {image!r}")
        for origin in self.cors_origins:
            if origin == "*" or not re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d{1,5})?", origin):
                raise ConfigError("REPLIC8_CORS_ORIGINS must list exact origins like https://app.example.com")
        if self.poll_interval_s and self.poll_interval_s < 30:
            raise ConfigError("REPLIC8_POLL_SECONDS must be 0 (off) or at least 30")
        for tool in self.write_allowlist:
            if not TOOL_NAME.match(tool):
                raise ConfigError(f"invalid tool name in REPLIC8_WRITE_OPS: {tool!r}")
