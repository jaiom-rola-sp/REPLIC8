"""Ask Nemotron for operations (FR-2) and for repairs after a legacy change (FR-7).

Results are only candidates. They go through guard.py here, then must pass
contract tests before registry.publish will serve them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from .guard import PROPOSAL_SCHEMA, Symbol, validate_proposal
from .models import Access, Operation, Tier
from .prompts import build_context, heal_messages, propose_messages

log = logging.getLogger("replic8.generate")


class JsonModel(Protocol):
    def complete_json(self, system: str, user: str, schema: dict | None = None) -> str: ...


@dataclass
class Generation:
    accepted: list[Operation] = field(default_factory=list)
    rejected: dict[str, str] = field(default_factory=dict)
    files_sent: list[str] = field(default_factory=list)
    examples: dict[str, list[dict]] = field(default_factory=dict)


def _ask(model: JsonModel, system: str, user: str, **validate_kwargs) -> tuple[list[Operation], dict[str, str]]:
    raw = model.complete_json(system, user, PROPOSAL_SCHEMA)
    validate_kwargs["examples_out"].clear()
    try:
        return validate_proposal(raw, **validate_kwargs)
    except ValueError as exc:
        # One retry. Only our own error message goes back, never the model's earlier text.
        log.info("proposal invalid, retrying once: %s", exc)
        retry = f"{user}\n\nYour previous answer was rejected: {exc}. Return only the JSON object."
        return validate_proposal(model.complete_json(system, retry, PROPOSAL_SCHEMA), **validate_kwargs)


def propose(model: JsonModel, *, namespace: str, tier: Tier, repo_root: Path, image: str,
            argv_for: Callable[[str, str], list[str]], symbols: list[Symbol] | None = None) -> Generation:
    ctx = build_context(repo_root, symbols)
    if not ctx.files:
        raise ValueError("no readable source files to send")
    system, user = propose_messages(namespace, tier, ctx, symbols)
    examples: dict[str, list[dict]] = {}
    accepted, rejected = _ask(model, system, user, namespace=namespace, tier=tier, repo_root=repo_root,
                              image=image, argv_for=argv_for, symbols=symbols, examples_out=examples)
    return Generation(accepted, rejected, ctx.files, examples)


def heal(model: JsonModel, *, namespace: str, tier: Tier, previous: list[Operation], diff: str,
         repo_root: Path, image: str, argv_for: Callable[[str, str], list[str]],
         symbols: list[Symbol] | None = None) -> Generation:
    """Repair operations for new code without changing what agents see.

    A repaired operation must keep its name and input schema, and must not turn a
    write into a read. It keeps the old output schema. Anything else is a breaking change and needs a human, so it is rejected.
    """
    ctx = build_context(repo_root, symbols)
    system, user = heal_messages(namespace, tier, ctx, previous, diff, symbols)
    accepted, rejected = _ask(model, system, user, namespace=namespace, tier=tier, repo_root=repo_root,
                              image=image, argv_for=argv_for, symbols=symbols, examples_out={})
    before = {op.tool: op for op in previous}
    kept: list[Operation] = []
    for op in accepted:
        old = before.get(op.tool)
        if old is None:
            rejected[op.tool] = "new operation; repairs may not add operations"
        elif op.input_schema != old.input_schema:
            rejected[op.tool] = "repair changed the input schema (breaking change, needs a human)"
        elif old.access is Access.write and op.access is Access.read:
            rejected[op.tool] = "repair tried to relabel a write operation as read"
        else:
            # The output schema is REPLIC8's (learned from real outputs); the replay of
            # recorded cases then proves the outputs are unchanged.
            kept.append(op.model_copy(update={"output_schema": old.output_schema}))
    for tool in before:
        if tool not in {op.tool for op in kept} and tool not in rejected:
            rejected[tool] = "dropped by the repair"
    return Generation(kept, rejected, ctx.files)
