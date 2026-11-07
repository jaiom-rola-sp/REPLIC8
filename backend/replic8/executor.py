"""Call one published operation in the sandbox and check its result against the schema.

Shared by the gateway (live calls) and contract tests (verification), so both go
through exactly the same path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .models import Operation, WrapperVersion
from .sandbox import Sandbox


class CallError(Exception):
    """Safe-to-show failure. The message never includes legacy stderr or stack traces."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def checkout_dir(repos_root: Path, version: WrapperVersion) -> Path:
    # repo_url is canonical (https://github.com/owner/repo.git) because ingest wrote it.
    owner, repo = version.repo_url.removesuffix(".git").split("/")[-2:]
    return repos_root / f"{owner.lower()}__{repo.lower()}" / version.source_commit


def validate_input(op: Operation, payload: Any) -> None:
    errors = list(Draft202012Validator(op.input_schema).iter_errors(payload))
    if errors:
        raise CallError(f"input does not match the schema: {errors[0].message[:200]}", status=422)


class Executor:
    def __init__(self, sandbox: Sandbox, repos_root: Path):
        self.sandbox = sandbox
        self.repos_root = repos_root

    def call(self, op: Operation, version: WrapperVersion, payload: dict[str, Any]) -> dict[str, Any]:
        validate_input(op, payload)
        result = self.sandbox.run(
            op.invocation.image,
            checkout_dir(self.repos_root, version),
            op.invocation.argv,
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        )
        if result.timed_out:
            raise CallError("legacy system timed out", status=504)
        if result.output_too_large:
            raise CallError("legacy system returned too much data")
        if result.exit_code != 0:
            raise CallError("legacy system returned an error")
        try:
            output = json.loads(result.stdout)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CallError("legacy system returned invalid JSON") from exc
        # Output is checked too, so a broken or manipulated wrapper can't return
        # arbitrary data to the agent under a trusted schema.
        if list(Draft202012Validator(op.output_schema).iter_errors(output)):
            raise CallError("legacy system output does not match the published schema")
        return output
