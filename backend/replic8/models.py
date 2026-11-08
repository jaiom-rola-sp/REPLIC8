"""Data model for systems, operations and wrapper versions.

Every operation carries the trust facts the PRD requires: ingestion tier (FR-11),
read/write access (FR-13), source location (FR-2) and its contract test result (FR-3).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, Field, field_validator, model_validator

NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
OP_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


class Tier(str, Enum):
    parsed = "parsed"
    inferred = "inferred"
    black_box = "black-box"


class Access(str, Enum):
    read = "read"
    write = "write"


def _check_schema(schema: dict[str, Any]) -> dict[str, Any]:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"invalid JSON schema: {exc.message}") from exc
    if schema.get("type") != "object":
        raise ValueError("schema must describe a JSON object")
    return schema


class SourceLocation(BaseModel):
    file: str
    line: int = Field(ge=1)

    @field_validator("file")
    @classmethod
    def _relative_inside_repo(cls, value: str) -> str:
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError("source file must be a relative path inside the repo")
        return value

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"


class Invocation(BaseModel):
    """How the sandbox runs an operation.

    The argv is fixed at generation time. Caller input never becomes an argument:
    it is sent as JSON on stdin, so it can't inject flags or shell syntax.
    """

    image: str = Field(pattern=r"^[a-z0-9][a-z0-9._/-]{0,127}(:[A-Za-z0-9._-]{1,128})?(@sha256:[0-9a-f]{64})?$")
    argv: list[str] = Field(min_length=1, max_length=32)

    @field_validator("argv")
    @classmethod
    def _no_control_chars(cls, argv: list[str]) -> list[str]:
        for arg in argv:
            if not arg or len(arg) > 512 or any(ord(c) < 32 for c in arg):
                raise ValueError("argv entries must be non-empty printable strings")
        return argv


class Operation(BaseModel):
    namespace: str
    name: str
    description: str = Field(max_length=500)
    tier: Tier
    access: Access
    source: SourceLocation
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    invocation: Invocation

    @field_validator("namespace")
    @classmethod
    def _ns(cls, v: str) -> str:
        if not NAME.match(v):
            raise ValueError("namespace must match ^[a-z][a-z0-9_]{0,31}$")
        return v

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not OP_NAME.match(v):
            raise ValueError("operation name must match ^[a-z][a-z0-9_]{0,63}$")
        return v

    @field_validator("input_schema", "output_schema")
    @classmethod
    def _schema(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _check_schema(v)

    @property
    def tool(self) -> str:
        return f"{self.namespace}.{self.name}"


class ContractTestResult(BaseModel):
    passed: bool
    cases: int = Field(ge=0)
    source_commit: str
    ran_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    detail: str = Field(default="", max_length=500)

    @field_validator("source_commit")
    @classmethod
    def _commit(cls, v: str) -> str:
        if not COMMIT.match(v):
            raise ValueError("source_commit must be a full 40-character git SHA")
        return v


class ContractCase(BaseModel):
    """One recorded call: this input gave this output on the tested commit.

    Self-heal replays these exact inputs and requires identical outputs, so a
    repair can't silently change what agents get back.
    """

    input: dict[str, Any]
    output: dict[str, Any]


class WrapperVersion(BaseModel):
    system: str
    version: int = Field(ge=1)
    source_commit: str
    repo_url: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    operations: list[Operation]
    tests: dict[str, ContractTestResult]
    cases: dict[str, list[ContractCase]] = Field(default_factory=dict)
    rejected: dict[str, str] = Field(default_factory=dict)
    parent_version: int | None = None
    reason: str = Field(default="onboarded", max_length=100)

    @field_validator("system")
    @classmethod
    def _system(cls, v: str) -> str:
        if not NAME.match(v):
            raise ValueError("system must match ^[a-z][a-z0-9_]{0,31}$")
        return v

    @model_validator(mode="after")
    def _every_op_is_verified(self) -> "WrapperVersion":
        names = [op.tool for op in self.operations]
        if len(names) != len(set(names)):
            raise ValueError("duplicate operation names")
        for op in self.operations:
            if op.namespace != self.system:
                raise ValueError(f"{op.tool} is not in namespace {self.system}")
            result = self.tests.get(op.tool)
            if result is None or not result.passed or result.cases < 1:
                raise ValueError(f"{op.tool} has no passing contract test")
            if result.source_commit != self.source_commit:
                raise ValueError(f"{op.tool} was tested against a different commit")
        return self
