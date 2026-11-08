"""Settings read from environment variables. Secrets never live in the repo (NFR Security)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

MIN_TOKEN_LENGTH = 32
TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}\.[a-z][a-z0-9_]{0,63}$")


class ConfigError(ValueError):
    pass


def _csv(name: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


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
    # Write operations stay disabled unless named here (FR-13). Empty in v1.
    write_allowlist: frozenset[str] = frozenset()
    # Docker images the sandbox may run. Pin by digest in real deployments.
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
        for origin in self.cors_origins:
            if origin == "*" or not re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d{1,5})?", origin):
                raise ConfigError("REPLIC8_CORS_ORIGINS must list exact origins like https://app.example.com")
        if self.poll_interval_s and self.poll_interval_s < 30:
            raise ConfigError("REPLIC8_POLL_SECONDS must be 0 (off) or at least 30")
        for tool in self.write_allowlist:
            if not TOOL_NAME.match(tool):
                raise ConfigError(f"invalid tool name in REPLIC8_WRITE_OPS: {tool!r}")
