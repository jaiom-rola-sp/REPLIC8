"""Known-good values: contract tests must be able to hit real records (a model-invented ID returns
"not found", which passes but proves nothing), and a model-written pattern must not lock real IDs out."""

from jsonschema import Draft202012Validator

from conftest import make_op
from replic8.pipeline import _accept_known, _known_inputs, _valid_inputs
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


def test_a_pattern_that_rejects_a_real_id_is_dropped_but_length_stays():
    op = op_with(STRICT)
    given = [{"request_id": "R-1001"}]
    assert _valid_inputs(op, given) == []                     # before: the real ID would be thrown away
    fixed = _accept_known(op, given)
    props = fixed.input_schema["properties"]["request_id"]
    assert "pattern" not in props and props["maxLength"] == 8
    assert _valid_inputs(fixed, given) == given
    assert not Draft202012Validator(fixed.input_schema).is_valid({"request_id": "R-1001-TOO-LONG"})  # still bounded


def test_a_pattern_is_kept_when_it_is_not_what_rejects_the_value():
    op = op_with(STRICT)
    assert _accept_known(op, [{"request_id": "R-1001-TOO-LONG"}]) is op   # too long: the pattern is not to blame
    assert _accept_known(op, [{"request_id": "R1001"}]) is op              # already valid: nothing to change
    assert _accept_known(op, [{"other": "R-1"}, "not a dict", {"request_id": 5}]) is op


def test_the_prompt_no_longer_asks_for_patterns_and_warns_about_hyphens():
    assert "patterns where obvious" not in RULES
    assert "never exclude them" in RULES
