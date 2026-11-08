"""Check what the model proposes before anything uses it (PRD section 8).

Nemotron reads untrusted legacy code, so its output can be wrong or steered by
text planted in that code (prompt injection). The model only ever produces a
declarative JSON proposal. Nothing it writes is executed on the host. This module:
- parses the proposal strictly and rejects anything outside the schema,
- for the `parsed` tier, requires each operation to match a symbol tree-sitter
  actually extracted (exact name, file and line),
- for other tiers, requires the cited file:line to exist in the checkout,
- never takes a command or code from the model,
- never lets the model downgrade a write-looking function to `read` (FR-13).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from .models import Access, Operation, SourceLocation, Tier

MAX_PROPOSAL_BYTES = 200_000
MAX_OPERATIONS = 20
SHELLS = {"sh", "bash", "zsh", "dash", "ash", "ksh", "csh", "tcsh", "fish", "busybox", "env",
          "cmd", "cmd.exe", "powershell", "pwsh", "eval", "xargs"}

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
                             "input_schema", "output_schema"],
                "properties": {
                    "name": {"type": "string"},
                    "symbol": {"type": "string", "maxLength": 200},
                    "file": {"type": "string", "maxLength": 300},
                    "line": {"type": "integer", "minimum": 1},
                    "access": {"enum": ["read", "write"]},
                    "description": {"type": "string", "maxLength": 500},
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "examples": {"type": "array", "maxItems": 3, "items": {"type": "object"}},
                    # Only for a command-line program: the fixed form REPLIC8 turns into the command.
                    "cli": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["args", "output"],
                        "properties": {
                            "args": {"type": "array", "maxItems": 20, "items": {"type": "string", "maxLength": 80}},
                            "output": {"enum": ["json", "keyvalue", "lines"]},
                        },
                    },
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
    # For a function that is called by name (Python): (parameter name, required) in order.
    params: tuple[tuple[str, bool], ...] = ()
    # A whole program run from a command line (not a function). `help` is what it printed for --help:
    # untrusted text, shown to the model only as data.
    program: bool = False
    help: str = ""


CLI_LITERAL = re.compile(r"^[A-Za-z0-9_./:,@%+=-]{1,64}$")
CLI_SLOT = re.compile(r"^(?:(--?[A-Za-z0-9][A-Za-z0-9_-]{0,40}=))?\{([A-Za-z_][A-Za-z0-9_]{0,63})\}$")


def cli_problem(cli: dict[str, Any], schema: dict[str, Any]) -> str:
    """Why a proposed command-line form is not allowed, or "" if it is.

    A caller's value only ever fills a whole argument ("{field}") or the part after "--flag=". The model
    never writes a command, never uses a shell, and every field it names must be a short scalar input.
    """
    props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    required = set(schema["required"]) if isinstance(schema.get("required"), list) else set()
    used: set[str] = set()
    args = cli["args"]
    for i, token in enumerate(args):
        slot = CLI_SLOT.match(token)
        if not slot:
            if not CLI_LITERAL.match(token):
                return f"argument {token[:30]!r} is not a plain literal or a {{field}} slot"
            continue
        prefix, field = slot.groups()
        spec = props.get(field)
        if not isinstance(spec, dict):
            return f"slot {{{field}}} is not an input field"
        kind = spec.get("type")
        if kind not in ("string", "integer", "number"):
            return f"slot {{{field}}} must be a string or number field"
        if kind == "string" and not isinstance(spec.get("maxLength"), int):
            return f"slot {{{field}}} needs a maxLength"
        if field in used:
            return f"slot {{{field}}} is used twice"
        used.add(field)
        if not prefix and field not in required and i > 0 and args[i - 1].startswith("-"):
            return f"optional {{{field}}} after a flag: use --flag={{{field}}}"
    if set(props) - used:
        return "every input field must appear in args (not: " + ", ".join(sorted(set(props) - used))[:100] + ")"
    return ""


def _params_problem(params: tuple[tuple[str, bool], ...], schema: dict[str, Any]) -> str:
    """Why a proposed input schema cannot call this function, or "" if it can."""
    names = {n for n, _ in params}
    required_params = {n for n, req in params if req}
    props = set(schema["properties"]) if isinstance(schema.get("properties"), dict) else set()
    listed = set(schema["required"]) if isinstance(schema.get("required"), list) else set()
    extra = props - names
    if extra:
        return "input fields must be the function's parameter names (not: " + ", ".join(sorted(extra))[:100] + ")"
    if required_params - props:
        return "missing required parameter(s): " + ", ".join(sorted(required_params - props))[:100]
    if required_params - listed:
        return "required must list every parameter that has no default"
    return ""


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


def examples_from(item: dict[str, Any], input_schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Model-suggested example inputs. Data only; kept only if they fit the input schema."""
    validator = Draft202012Validator(input_schema)
    kept = []
    for example in item.get("examples", []):
        if not list(validator.iter_errors(example)) and example not in kept:
            kept.append(example)
    return kept


def validate_proposal(
    raw: str,
    *,
    namespace: str,
    tier: Tier,
    repo_root: Path,
    image: str,
    argv_for: Callable[[str, str], list[str]],
    symbols: list[Symbol] | None = None,
    examples_out: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[list[Operation], dict[str, str]]:
    """Turn model output into candidate operations. Returns (accepted, rejected-with-reason).

    `image` and the command (`argv_for(symbol, file)`) are chosen by REPLIC8 per
    language, never by the model, so the model never writes code that runs.
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
    by_key = {(s.name, s.file, s.line): s for s in symbols or []}

    accepted: list[Operation] = []
    rejected: dict[str, str] = {}
    for item in data["operations"]:
        label = f"{namespace}.{item['name']}"
        if tier is Tier.parsed and (item["symbol"], item["file"], item["line"]) not in known:
            rejected[label] = "does not match an extracted symbol"
            continue
        symbol = by_key.get((item["symbol"], item["file"], item["line"]))
        cli = item.get("cli")
        if symbol is not None and symbol.program != (cli is not None):
            rejected[label] = ("a program needs a cli form" if symbol.program
                               else "cli is only for programs run from a command line")
            continue
        if cli is not None:
            problem = cli_problem(cli, item["input_schema"])
            if problem:
                rejected[label] = problem
                continue
        if symbol is not None and symbol.params:
            problem = _params_problem(symbol.params, item["input_schema"])
            if problem:
                rejected[label] = problem
                continue
        try:
            source = SourceLocation(file=item["file"], line=item["line"])
        except ValidationError:
            rejected[label] = "source location is outside the repo"
            continue
        if not _line_exists(repo_root, source.file, source.line):
            rejected[label] = "source location does not exist"
            continue
        argv = argv_for(item["symbol"], item["file"], cli) if cli is not None else argv_for(item["symbol"], item["file"])
        if not argv or Path(argv[0]).name.lower() in SHELLS:
            rejected[label] = "no safe command for this symbol"
            continue
        try:
            op = Operation(
                namespace=namespace,
                name=item["name"],
                description=item["description"],
                tier=Tier.black_box if cli is not None else tier,
                access=decide_access(item["symbol"], item["access"]),
                source=source,
                input_schema=item["input_schema"],
                output_schema=item["output_schema"],
                invocation={"image": image, "argv": argv},
            )
        except ValidationError as exc:
            rejected[label] = f"invalid operation: {exc.errors()[0]['msg'][:200]}"
            continue
        if any(o.tool == op.tool for o in accepted):
            rejected[label] = "duplicate operation name"
            continue
        accepted.append(op)
        if examples_out is not None:
            examples_out[op.tool] = examples_from(item, op.input_schema)
    return accepted, rejected
