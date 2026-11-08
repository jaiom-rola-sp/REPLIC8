"""Call one operation in the sandbox and check its result against the schema.

Shared by the gateway (live calls), contract tests (verification) and self-heal
(replays), so all three go through exactly the same path: Sandbox.run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .models import Operation, WrapperVersion
from .sandbox import (SHIM_FUNCTION_MISSING, SHIM_VALUE_REFUSED, FunctionMissing, OutputSchemaError, Sandbox, SandboxCrash,
                      SandboxError, SandboxTimeout)


class CallError(SandboxError):
    """Bad caller input. Raised before any legacy code runs."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def repo_key(repo_url: str) -> str:
    """Folder name for a repo: owner__repo for GitHub, local__name for local demo repos."""
    owner, repo = repo_url.removesuffix(".git").rstrip("/").split("/")[-2:]
    return f"{owner.lower()}__{repo.lower()}"


def checkout_dir(repos_root: Path, version: WrapperVersion) -> Path:
    return repos_root / repo_key(version.repo_url) / version.source_commit


def validate_input(op: Operation, payload: Any) -> None:
    errors = list(Draft202012Validator(op.input_schema).iter_errors(payload))
    if errors:
        raise CallError(f"input does not match the schema: {errors[0].message[:200]}")


class Executor:
    def __init__(self, sandbox: Sandbox, repos_root: Path):
        self.sandbox = sandbox
        self.repos_root = repos_root
        self.builds_root = sandbox.builds_root

    def call(self, op: Operation, version: WrapperVersion, payload: dict[str, Any]) -> dict[str, Any]:
        return self.call_at(op, version.repo_url, version.source_commit, payload)

    def call_at(self, op: Operation, repo_url: str, commit: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Run `op` against a specific checkout. Raises a SandboxError subclass on failure."""
        validate_input(op, payload)
        key = repo_key(repo_url)
        build = self.builds_root / key / commit
        result = self.sandbox.run(
            op.invocation.image,
            self.repos_root / key / commit,
            op.invocation.argv,
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            build_dir=build if build.is_dir() else None,
        )
        if result.timed_out:
            raise SandboxTimeout("legacy system timed out")
        if result.output_too_large:
            raise SandboxCrash("legacy system returned too much data")
        if result.exit_code == SHIM_VALUE_REFUSED:
            raise CallError("an input value was refused: it must be short printable text and not start with '-'")
        if result.exit_code == SHIM_FUNCTION_MISSING:
            raise FunctionMissing("legacy system no longer has this function")
        if result.exit_code != 0:
            raise SandboxCrash("legacy system returned an error")
        try:
            output = json.loads(result.stdout)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SandboxCrash("legacy system returned invalid JSON") from exc
        # Output is checked too, so a broken or manipulated wrapper can't return
        # arbitrary data to the agent under a trusted schema.
        if not isinstance(output, dict) or list(Draft202012Validator(op.output_schema).iter_errors(output)):
            raise OutputSchemaError("legacy system output does not match the published schema")
        return output
