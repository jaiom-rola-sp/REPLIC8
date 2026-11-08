"""Contract tests (FR-3): run each operation against the real legacy program.

An operation passes when every case runs in the sandbox, its output matches the
published output schema, and a repeat of the first case gives the same output
(so the recorded outputs are stable enough to replay). The passing input/output
pairs are recorded with the version. Self-heal later replays those exact inputs
on the new code and requires identical outputs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .executor import Executor
from .models import ContractCase, ContractTestResult, Operation
from .sandbox import SandboxError

log = logging.getLogger("replic8.contracts")
MAX_CASES = 5


@dataclass
class ContractRun:
    result: ContractTestResult
    cases: list[ContractCase] = field(default_factory=list)
    output_schema: dict[str, Any] | None = None


_JSON = {bool: "boolean", int: "integer", float: "number", str: "string", type(None): "null"}


def observed_schema(values: list[Any]) -> dict[str, Any]:
    """A JSON schema describing values the legacy program really returned.

    Fields present in every observed object are required; others are optional.
    Extra fields are allowed, so a lookup that returns more detail for a found
    record still validates.
    """
    values = list(values)
    if values and all(isinstance(v, dict) for v in values):
        keys = sorted({k for v in values for k in v})
        return {"type": "object",
                "properties": {k: observed_schema([v[k] for v in values if k in v]) for k in keys},
                "required": [k for k in keys if all(k in v for v in values)]}
    if values and all(isinstance(v, list) for v in values):
        items = [i for v in values for i in v]
        return {"type": "array", "items": observed_schema(items) if items else {}}
    types = sorted({_JSON.get(type(v), "string") for v in values})
    if set(types) == {"integer", "number"}:
        types = ["number"]
    return {"type": types[0]} if len(types) == 1 else {"type": types} if types else {}


def run_contract(executor: Executor, op: Operation, repo_url: str, commit: str,
                 inputs: list[dict[str, Any]], learn_schema: bool = False) -> ContractRun:
    """Record cases for a new operation. Fails if there are no usable inputs.

    With learn_schema, the model's guessed output schema is not trusted: outputs
    are recorded as returned, and the published output schema is derived from them.
    """
    if learn_schema:
        op = op.model_copy(update={"output_schema": {"type": "object"}})
    inputs = _unique(inputs)[:MAX_CASES]
    if not inputs:
        return ContractRun(ContractTestResult(passed=False, cases=0, source_commit=commit,
                                              detail="no example inputs to test with"))
    cases: list[ContractCase] = []
    for payload in inputs:
        try:
            output = executor.call_at(op, repo_url, commit, payload)
        except SandboxError as exc:
            return ContractRun(_fail(commit, len(cases), type(exc).__name__, str(exc)))
        cases.append(ContractCase(input=payload, output=output))
    try:
        repeat = executor.call_at(op, repo_url, commit, cases[0].input)
    except SandboxError as exc:
        return ContractRun(_fail(commit, len(cases), type(exc).__name__, str(exc)))
    if repeat != cases[0].output:
        return ContractRun(_fail(commit, len(cases), "Unstable", "same input gave different outputs"))
    schema = observed_schema([c.output for c in cases]) if learn_schema else None
    return ContractRun(ContractTestResult(passed=True, cases=len(cases), source_commit=commit), cases, schema)


def replay_contract(executor: Executor, op: Operation, repo_url: str, commit: str,
                    recorded: list[ContractCase]) -> ContractRun:
    """Replay recorded cases on a (possibly repaired) operation; outputs must be identical."""
    if not recorded:
        return ContractRun(_fail(commit, 0, "NoCases", "no recorded cases to replay"))
    for i, case in enumerate(recorded):
        try:
            output = executor.call_at(op, repo_url, commit, case.input)
        except SandboxError as exc:
            return ContractRun(_fail(commit, i, type(exc).__name__, str(exc)))
        if output != case.output:
            return ContractRun(_fail(commit, i, "Changed", "output differs from the recorded contract"))
    return ContractRun(ContractTestResult(passed=True, cases=len(recorded), source_commit=commit),
                       list(recorded))


def _fail(commit: str, cases: int, kind: str, message: str) -> ContractTestResult:
    return ContractTestResult(passed=False, cases=cases, source_commit=commit, detail=f"{kind}: {message}"[:500])


def _unique(inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    for item in inputs:
        if isinstance(item, dict) and item not in seen:
            seen.append(item)
    return seen
