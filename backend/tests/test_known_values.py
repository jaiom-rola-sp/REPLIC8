"""Known-good values: contract tests must be able to hit real records (a model-invented ID returns
"not found", which passes but proves nothing), and a model-written pattern must not lock real IDs out."""

from jsonschema import Draft202012Validator

from conftest import make_op
from replic8.pipeline import _known_inputs, _usable_known_inputs, _valid_inputs, fit_input_schema
from replic8.prompts import RULES


def op_with(props: dict):
    return make_op().model_copy(update={"input_schema": {
        "type": "object", "properties": props, "required": list(props), "additionalProperties": False}})


STRICT = {"request_id": {"type": "string", "maxLength": 8, "pattern": "^[A-Za-z0-9 ]*$"}}  # what the live model wrote


def test_known_values_become_inputs_only_for_operations_whose_fields_are_all_known():
    stock = op_with({"part_id": {"type": "string"}, "destination": {"type": "string"}})
    known = {"part_id": ["PMP-2210", "VLV-0450"], "destination": ["PERMIAN"]}
    assert _known_inputs(stock, known) == [{"part_id": "PMP-2210", "destination": "PERMIAN"},
                                           {"part_id": "VLV-0450", "destination": "PERMIAN"}]
    assert _known_inputs(stock, {"part_id": ["PMP-2210"]}) == []  # destination unknown: no guessing
    assert _known_inputs(op_with({}), known) == []


def test_known_values_win_over_a_model_written_pattern():
    op = op_with(STRICT)
    given = _usable_known_inputs(op, {"request_id": ["R-1001"]})
    assert given == [{"request_id": "R-1001"}]
    assert _valid_inputs(op, given) == []                      # before: the real ID would be thrown away
    fitted = fit_input_schema(op.input_schema, given)
    props = fitted["properties"]["request_id"]
    assert "pattern" not in props and props["maxLength"] == 8  # the pattern goes; the length stays
    assert _valid_inputs(op.model_copy(update={"input_schema": fitted}), given) == given
    assert not Draft202012Validator(fitted).is_valid({"request_id": "R-1001-TOO-LONG"})


def test_a_known_value_of_the_wrong_type_is_skipped_instead_of_rejecting_the_operation():
    counted = op_with({"quantity": {"type": "integer"}})
    assert _usable_known_inputs(counted, {"quantity": ["abc"]}) == []
    assert _usable_known_inputs(op_with({"request_id": {"type": "string"}}), {"request_id": ["R-1"]}) == [{"request_id": "R-1"}]


def test_the_prompt_no_longer_asks_for_patterns_and_warns_about_hyphens():
    assert "patterns where obvious" not in RULES
    assert "never exclude them" in RULES
