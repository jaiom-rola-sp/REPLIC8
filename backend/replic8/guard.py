"""Check what the model proposes before anything uses it (PRD section 8).

Nemotron reads untrusted legacy code, so its output can be wrong or steered by
text planted in that code (prompt injection). The model only ever produces a
declarative JSON proposal. Nothing it writes is executed on the host. This module:
- parses the proposal strictly and rejects anything outside the schema,
- for the `parsed` tier, requires each operation to match a symbol tree-sitter
  actually extracted (exact name, file and line),
- for other tiers, requires the cited file:line to exist in the checkout,
- never lets the model downgrade a write-looking function to `read` (FR-13).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from .models import Access, Operation, SourceLocation, Tier

MAX_PROPOSAL_BYTES = 200_000
MAX_OPERATIONS = 20

WRITE_VERBS = {
    "add", "append", "approve", "assign", "book", "buy", "cancel", "charge", "close", "commit",
    "create", "delete", "deposit", "destroy", "disable", "dispatch", "drop", "edit", "enable",
    "exec", "execute", "import", "insert", "issue", "kill", "load", "merge", "modify", "move",
    "order", "patch", "pay", "post", "purchase", "purge", "put", "receive", "refund", "register",
    "reject", "remove", "rename", "replace", "reserve", "reset", "restore", "run", "save", "schedule",
    "send", "set", "ship", "start", "stop", "store", "submit", "sync", "transfer", "truncate",
    "unlock", "update", "upload", "upsert", "withdraw", "write",
}

PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["operations"],
    "properties": {
        "operations": {
            "type": "array",
            "maxItems": MAX_OPERATIONS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "symbol", "file", "line", "access", "description",
                             "input_schema", "output_schema", "argv"],
                "properties": {
                    "name": {"type": "string"},
                    "symbol": {"type": "string", "maxLength": 200},
                    "file": {"type": "string", "maxLength": 300},
                    "line": {"type": "integer", "minimum": 1},
                    "access": {"enum": ["read", "write"]},
                    "description": {"type": "string", "maxLength": 500},
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "argv": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 32},
                },
            },
        }
    },
}
_PROPOSAL_VALIDATOR = Draft202012Validator(PROPOSAL_SCHEMA)


@dataclass(frozen=True)
class Symbol:
    name: str
    file: str
    line: int


def _words(name: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return [w.lower() for w in re.split(r"[^A-Za-z0-9]+", spaced) if w]


def decide_access(symbol_name: str, claimed: str) -> Access:
    """The model may upgrade read to write, never the reverse for write-looking names."""
    if claimed == Access.write.value:
        return Access.write
    if any(word in WRITE_VERBS for word in _words(symbol_name)):
        return Access.write
    return Access.read


def _line_exists(repo_root: Path, file: str, line: int) -> bool:
    root = repo_root.resolve()
    path = (root / file).resolve()
    if root not in path.parents or not path.is_file() or path.is_symlink():
        return False
    with path.open("rb") as fh:
        for count, _ in enumerate(fh, start=1):
            if count >= line:
                return True
    return False


def validate_proposal(
    raw: str,
    *,
    namespace: str,
    tier: Tier,
    repo_root: Path,
    image: str,
    symbols: list[Symbol] | None = None,
) -> tuple[list[Operation], dict[str, str]]:
    """Turn model output into candidate operations. Returns (accepted, rejected-with-reason).

    `image` is chosen by Replic8 per language, never by the model.
    Accepted operations are still only candidates: they must pass contract tests
    before the registry will publish them.
    """
    if len(raw.encode("utf-8")) > MAX_PROPOSAL_BYTES:
        raise ValueError("proposal too large")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("proposal is not valid JSON") from exc
    errors = sorted(_PROPOSAL_VALIDATOR.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        raise ValueError(f"proposal does not match the schema: {errors[0].message[:200]}")

    if tier is Tier.parsed and not symbols:
        raise ValueError("parsed tier needs the extracted symbol list")
    known = {(s.name, s.file, s.line) for s in symbols or []}

    accepted: list[Operation] = []
    rejected: dict[str, str] = {}
    for item in data["operations"]:
        label = f"{namespace}.{item['name']}"
        if tier is Tier.parsed and (item["symbol"], item["file"], item["line"]) not in known:
            rejected[label] = "does not match an extracted symbol"
            continue
        try:
            source = SourceLocation(file=item["file"], line=item["line"])
        except ValidationError:
            rejected[label] = "source location is outside the repo"
            continue
        if not _line_exists(repo_root, source.file, source.line):
            rejected[label] = "source location does not exist"
            continue
        try:
            op = Operation(
                namespace=namespace,
                name=item["name"],
                description=item["description"],
                tier=tier,
                access=decide_access(item["symbol"], item["access"]),
                source=source,
                input_schema=item["input_schema"],
                output_schema=item["output_schema"],
                invocation={"image": image, "argv": item["argv"]},
            )
        except ValidationError as exc:
            rejected[label] = f"invalid operation: {exc.errors()[0]['msg'][:200]}"
            continue
        if any(o.tool == op.tool for o in accepted):
            rejected[label] = "duplicate operation name"
            continue
        accepted.append(op)
    return accepted, rejected
