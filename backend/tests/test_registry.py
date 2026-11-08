import json

import pytest
from pydantic import ValidationError

from replic8.models import ContractTestResult, SourceLocation
from replic8.registry import Registry, RegistryError

from conftest import COMMIT, OTHER_COMMIT, make_op, passed

URL = "https://github.com/acme/legacy.git"


def test_only_passing_operations_are_published(data_dir):
    reg = Registry(data_dir)
    ops = [make_op("get_request"), make_op("list_parts"), make_op("get_status"), make_op("untested")]
    tests = {
        "maintenance.get_request": passed(),
        "maintenance.list_parts": ContractTestResult(passed=False, cases=2, source_commit=COMMIT),
        "maintenance.get_status": passed(OTHER_COMMIT),
    }
    version = reg.publish("maintenance", URL, COMMIT, ops, tests)
    assert [op.name for op in version.operations] == ["get_request"]
    assert version.rejected == {
        "maintenance.list_parts": "contract test failed",  # no detail recorded
        "maintenance.get_status": "tested against a different commit",
        "maintenance.untested": "no contract test",
    }


def test_nothing_published_when_all_fail(data_dir):
    reg = Registry(data_dir)
    with pytest.raises(RegistryError):
        reg.publish("maintenance", URL, COMMIT, [make_op()], {})
    assert reg.current("maintenance") is None


def test_versions_and_rollback(data_dir):
    reg = Registry(data_dir)
    reg.publish("maintenance", URL, COMMIT, [make_op()], {"maintenance.get_request": passed()})
    reg.publish("maintenance", URL, OTHER_COMMIT, [make_op()], {"maintenance.get_request": passed(OTHER_COMMIT)})
    assert reg.versions("maintenance") == [1, 2]
    assert reg.current("maintenance").source_commit == OTHER_COMMIT
    reg.rollback("maintenance", 1)
    assert reg.current("maintenance").version == 1
    assert reg.versions("maintenance") == [1, 2]  # old versions are kept


def test_hand_edited_untested_operation_is_refused_on_load(data_dir):
    reg = Registry(data_dir)
    reg.publish("maintenance", URL, COMMIT, [make_op()], {"maintenance.get_request": passed()})
    path = reg.root / "maintenance" / "v1.json"
    data = json.loads(path.read_text())
    data["operations"].append(json.loads(make_op("sneaky").model_dump_json()))
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationError):
        reg.current("maintenance")


@pytest.mark.parametrize("name", ["../etc", "Maint", "a/b", "", "x" * 40])
def test_system_names_cannot_escape_registry(data_dir, name):
    with pytest.raises(RegistryError):
        Registry(data_dir).versions(name)


@pytest.mark.parametrize("path", ["/etc/passwd", "../secret.py", "a/../../b.py", "a\\b.py", ""])
def test_source_location_must_stay_in_repo(path):
    with pytest.raises(ValidationError):
        SourceLocation(file=path, line=1)
