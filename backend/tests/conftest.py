from __future__ import annotations

from pathlib import Path

import pytest

from replic8.config import token_id
from replic8.models import ContractTestResult, Operation

COMMIT = "a" * 40
OTHER_COMMIT = "b" * 40
TOKEN = "t" * 40
# Gateway tokens are fail-closed: without scopes they can call nothing.
ALL_SCOPES = {token_id(TOKEN): frozenset({"maintenance.*", "inventory.*"})}


def make_op(name: str = "get_request", access: str = "read", ns: str = "maintenance") -> Operation:
    return Operation(
        namespace=ns,
        name=name,
        description="Look up a maintenance request",
        tier="parsed",
        access=access,
        source={"file": "src/maint.py", "line": 3},
        input_schema={"type": "object", "properties": {"id": {"type": "string", "maxLength": 20}},
                      "required": ["id"], "additionalProperties": False},
        output_schema={"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
        invocation={"image": "python:3.12-alpine", "argv": ["python", "wrapper.py", name]},
    )


def passed(commit: str = COMMIT) -> ContractTestResult:
    return ContractTestResult(passed=True, cases=2, source_commit=commit)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"
