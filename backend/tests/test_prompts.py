"""The propose prompt (FR-2): it tells the model how calls really work, and a proposal
that follows its rules is accepted by the guard and the Operation model."""

import json
from pathlib import Path

from replic8.extract import extract_symbols
from replic8.guard import validate_proposal
from replic8.models import Tier
from replic8.prompts import build_context, propose_messages
from replic8.runtimes import LEGACY_IMAGE, argv_for, callable_symbols

ROOT = Path(__file__).resolve().parents[2]
B = ROOT / "legacy" / "b-maintenance-cobol"


def test_prompt_explains_call_protocol_names_and_descriptions():
    system, _ = propose_messages("maintenance", Tier.parsed, build_context(B))
    system = " ".join(system.split())  # ignore line wrapping
    # How replic8 calls the program, so schema names match the legacy keys.
    assert "part_id -> PART-ID" in system
    assert "ON-HAND -> on_hand" in system
    assert '"items"' in system and '"count"' in system
    # Keep legacy names so systems link by field name (F3).
    assert "Never rename" in system
    # Agent-facing descriptions on the operation and every property.
    assert "when an agent should use it" in system
    assert 'Every property in both schemas' in system
    # Strict inputs, lenient outputs.
    assert '"additionalProperties": false and a "maxLength" on every string' in system
    assert 'Take each "maxLength" from the field size in the code' in system
    assert 'Don\'t set "additionalProperties": false on outputs' in system


def test_rule_following_proposal_is_accepted():
    symbols = callable_symbols(B, extract_symbols(B)[0])
    line = {s.name: s.line for s in symbols}["GET-REQUEST"]
    proposal = {"operations": [{
        "name": "get_request",
        "symbol": "GET-REQUEST",
        "file": "src/MAINT.cbl",
        "line": line,
        "access": "read",
        "description": "Look up one maintenance request by its ID. Use it to find which part a "
                       "well needs and where. Returns found = \"N\" when no request matches.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["request_id"],
            "properties": {
                "request_id": {"type": "string", "maxLength": 8,
                               "description": "Maintenance request ID (8 characters)."},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["found", "request_id"],
            "properties": {
                "found": {"type": "string", "description": "Y if the request exists, N if not."},
                "request_id": {"type": "string", "description": "The request ID looked up."},
                "well_id": {"type": "string", "description": "Well the request is for."},
                "part_id": {"type": "string", "description": "Part needed for the repair."},
                "site": {"type": "string", "description": "Region where the well is."},
                "quantity": {"type": "integer", "description": "How many parts are needed."},
                "priority": {"type": "string", "description": "Request priority."},
                "status": {"type": "string", "description": "Request status, e.g. OPEN."},
                "opened": {"type": "string", "description": "Date the request was opened."},
            },
        },
    }]}
    accepted, rejected = validate_proposal(
        json.dumps(proposal), namespace="maintenance", tier=Tier.parsed, repo_root=B,
        image=LEGACY_IMAGE, argv_for=argv_for, symbols=symbols)
    assert rejected == {}
    assert [op.tool for op in accepted] == ["maintenance.get_request"]
    assert accepted[0].output_schema["properties"]["part_id"]["description"]
