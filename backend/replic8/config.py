"""Settings read from environment variables. Secrets never live in the repo (NFR Security)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

MIN_TOKEN_LENGTH = 32
E164 = re.compile(r"^\+[1-9]\d{6,14}$")
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
    # Write operations stay disabled unless named here (FR-13). Empty in v1.
    write_allowlist: frozenset[str] = frozenset()
    # Docker images the sandbox may run. Pin by digest in real deployments.
    sandbox_images: frozenset[str] = frozenset()
    sandbox: SandboxLimits = field(default_factory=SandboxLimits)
    max_repo_bytes: int = 200 * 1024 * 1024
    max_repo_files: int = 20_000
    clone_timeout_s: float = 120.0
    rate_limit_per_minute: int = 120
    notify_numbers: frozenset[str] = frozenset()

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            data_dir=Path(os.environ.get("REPLIC8_DATA_DIR", "./data")).resolve(),
            gateway_tokens=frozenset(_csv("REPLIC8_GATEWAY_TOKENS")),
            write_allowlist=frozenset(_csv("REPLIC8_WRITE_OPS")),
            sandbox_images=frozenset(_csv("REPLIC8_SANDBOX_IMAGES")),
            notify_numbers=frozenset(_csv("REPLIC8_NOTIFY_NUMBERS")),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        for token in self.gateway_tokens:
            if len(token) < MIN_TOKEN_LENGTH:
                raise ConfigError(f"gateway tokens must be at least {MIN_TOKEN_LENGTH} characters")
        for tool in self.write_allowlist:
            if not TOOL_NAME.match(tool):
                raise ConfigError(f"invalid tool name in REPLIC8_WRITE_OPS: {tool!r}")
        for number in self.notify_numbers:
            if not E164.match(number):
                raise ConfigError("REPLIC8_NOTIFY_NUMBERS must be E.164 numbers like +15551234567")
