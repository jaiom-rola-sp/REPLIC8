"""Operation schema checks, including the one repair applied to model-written schemas."""

import pytest
from pydantic import ValidationError

from replic8.models import Operation

from conftest import make_op


def with_output(schema):
    return Operation.model_validate({**make_op().model_dump(mode="json"), "output_schema": schema})


def test_a_required_list_inside_properties_is_moved_beside_it():
    # What the model actually wrote for the Fortran repo's get_shipping_options.
    op = with_output({"type": "object", "properties": {
        "found": {"type": "string"}, "count": {"type": "integer"},
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "carrier": {"type": "string"}, "required": ["carrier", "not_a_field"]}}},
        "required": ["found", "count"]}})
    assert op.output_schema["required"] == ["found", "count"]
    assert "required" not in op.output_schema["properties"]
    inner = op.output_schema["properties"]["items"]["items"]
    assert inner["required"] == ["carrier"]  # names that aren't properties are dropped
    assert "required" not in inner["properties"]


def test_existing_required_is_kept_and_merged():
    op = with_output({"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "string"},
                                                       "required": ["b"]}, "required": ["a"]})
    assert op.output_schema["required"] == ["a", "b"]


def test_valid_schemas_are_unchanged():
    schema = {"type": "object", "properties": {"required": {"type": "string"}}, "required": ["required"]}
    assert with_output(schema).output_schema == schema  # a real field called "required" is left alone


def test_other_schema_mistakes_are_still_rejected():
    with pytest.raises(ValidationError, match="invalid JSON schema"):
        with_output({"type": "object", "properties": {"found": "string"}})
    with pytest.raises(ValidationError, match="must describe a JSON object"):
        with_output({"type": "array"})
