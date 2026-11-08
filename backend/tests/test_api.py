"""Gateway extras and their security rules, without Docker."""

import pytest
from fastapi.testclient import TestClient

from replic8.config import ConfigError, Settings
from replic8.contracts import replay_contract, run_contract
from replic8.events import EventLog
from replic8.gateway import create_app
from replic8.graph import build_graph
from replic8.models import ContractCase
from replic8.registry import Registry
from replic8.sandbox import FunctionMissing
from replic8.sources import SourceError, canonical_url, fetch

from conftest import COMMIT, TOKEN, make_op, passed

ADMIN = "a" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class Exec:
    def __init__(self, outputs=None, error=None):
        self.outputs = list(outputs or [])
        self.error = error

    def call(self, op, version, payload):
        if self.error:
            raise self.error
        return {"id": payload["id"]}

    def call_at(self, op, url, commit, payload):
        if self.error:
            raise self.error
        return self.outputs.pop(0) if self.outputs else {"id": payload["id"]}


@pytest.fixture
def reg(data_dir):
    r = Registry(data_dir)
    r.publish("maintenance", "https://github.com/acme/legacy.git", COMMIT, [make_op()],
              {"maintenance.get_request": passed()})
    return r


def client(data_dir, reg, **kw):
    settings = Settings(data_dir=data_dir, gateway_tokens=frozenset({TOKEN}), **kw)
    return TestClient(create_app(settings, reg, Exec()), base_url="http://127.0.0.1:8000")


def test_admin_api_is_off_without_admin_tokens(data_dir, reg):
    c = client(data_dir, reg)
    r = c.post("/v1/admin/systems", json={"system": "x", "repo_url": "https://github.com/a/b"}, headers=AUTH)
    assert r.status_code == 403


def test_gateway_token_cannot_use_admin_routes(data_dir, reg):
    c = client(data_dir, reg, admin_tokens=frozenset({ADMIN}))
    for path in ("/v1/admin/systems/maintenance/heal", "/v1/admin/systems/maintenance/check"):
        assert c.post(path, headers=AUTH).status_code == 401
    # Admin token works for reads too; without a pipeline, admin actions report 503.
    admin = {"Authorization": f"Bearer {ADMIN}"}
    assert c.get("/v1/operations", headers=admin).status_code == 200
    assert c.post("/v1/admin/systems/maintenance/heal", headers=admin).status_code == 503


def test_read_endpoints_need_a_token(data_dir, reg):
    c = client(data_dir, reg)
    for path in ("/v1/graph", "/v1/events", "/v1/systems", "/v1/openapi.json", "/v1/systems/maintenance/versions"):
        assert c.get(path).status_code == 401
        assert c.get(path, headers=AUTH).status_code == 200


def test_operations_view_keeps_dashboard_fields(data_dir, reg):
    op = client(data_dir, reg).get("/v1/operations", headers=AUTH).json()["operations"][0]
    for field in ("tool", "description", "tier", "access", "enabled", "source", "version", "source_commit",
                  "input_schema"):
        assert field in op  # web/src/Dashboard.jsx reads these


def test_openapi_lists_only_enabled_tools(data_dir):
    r = Registry(data_dir)
    r.publish("maintenance", "https://github.com/acme/legacy.git", COMMIT,
              [make_op(), make_op("delete_request", access="write")],
              {"maintenance.get_request": passed(), "maintenance.delete_request": passed()})
    spec = client(data_dir, r).get("/v1/openapi.json", headers=AUTH).json()
    assert list(spec["paths"]) == ["/v1/operations/maintenance.get_request"]
    assert spec["paths"]["/v1/operations/maintenance.get_request"]["post"]["security"] == [{"bearer": []}]


def test_cors_only_for_listed_origins(data_dir, reg):
    c = client(data_dir, reg, cors_origins=("http://127.0.0.1:5173",))
    ok = c.options("/v1/operations", headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "GET"})
    bad = c.options("/v1/operations", headers={"Origin": "https://evil.com", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
    assert "access-control-allow-origin" not in bad.headers


@pytest.mark.parametrize("kw", [
    {"cors_origins": ("*",)},
    {"cors_origins": ("https://a.com/path",)},
    {"admin_tokens": frozenset({TOKEN})},
    {"admin_tokens": frozenset({"short"})},
    {"poll_interval_s": 5},
])
def test_unsafe_config_is_refused(tmp_path, kw):
    with pytest.raises(ConfigError):
        Settings(data_dir=tmp_path, gateway_tokens=frozenset({TOKEN}), **kw).validate()


def test_events_strip_unsafe_text(tmp_path):
    log = EventLog(tmp_path)
    e = log.add("call_failed", system="maint<script>", detail="x\n$(rm -rf /) `id` <b>")
    assert "<" not in e["system"] and "$" not in e["detail"] and "`" not in e["detail"] and "\n" not in e["detail"]
    with pytest.raises(ValueError):
        log.add("made_up_kind")
    assert (tmp_path / "events.jsonl").read_text().count("\n") == 1


def test_graph_links_only_matching_fields(data_dir):
    r = Registry(data_dir)
    out_op = make_op("get_request").model_copy(update={"output_schema": {
        "type": "object", "properties": {"part_id": {"type": "string"}, "qty": {"type": "integer"}}}})
    in_op = make_op("check_stock", ns="inventory").model_copy(update={"input_schema": {
        "type": "object", "properties": {"part_id": {"type": "string"}, "qty": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"on_hand": {"type": "integer"}}}})
    r.publish("maintenance", "https://github.com/acme/b.git", COMMIT, [out_op], {out_op.tool: passed()})
    r.publish("inventory", "https://github.com/acme/c.git", COMMIT, [in_op], {in_op.tool: passed()})
    data = [e for e in build_graph(r)["edges"] if e["type"] == "data"]
    assert [(e["source"], e["target"], e["field"]) for e in data] == [
        ("maintenance.get_request", "inventory.check_stock", "part_id")]  # qty: types differ, no edge


def test_contract_needs_inputs_and_stable_output():
    op = make_op()
    assert not run_contract(Exec(), op, "u", COMMIT, []).result.passed
    flaky = Exec(outputs=[{"id": "1"}, {"id": "2"}])
    assert "Unstable" in run_contract(flaky, op, "u", COMMIT, [{"id": "1"}]).result.detail
    good = run_contract(Exec(), op, "u", COMMIT, [{"id": "1"}, {"id": "1"}, {"id": "2"}])
    assert good.result.passed and good.result.cases == 2  # duplicates dropped


def test_replay_requires_identical_output():
    op = make_op()
    recorded = [ContractCase(input={"id": "1"}, output={"id": "1"})]
    assert replay_contract(Exec(), op, "u", COMMIT, recorded).result.passed
    assert "Changed" in replay_contract(Exec(outputs=[{"id": "9"}]), op, "u", COMMIT, recorded).result.detail
    assert "FunctionMissing" in replay_contract(Exec(error=FunctionMissing()), op, "u", COMMIT, recorded).result.detail


def test_local_repos_are_off_by_default_and_confined(tmp_path):
    (tmp_path / "root" / "b").mkdir(parents=True)
    (tmp_path / "secret").mkdir()
    with pytest.raises(SourceError):
        canonical_url("local://b", None)
    for bad in ("local://../secret", "local://b/../../secret", "local://B", "local://"):
        with pytest.raises(Exception):
            canonical_url(bad, tmp_path / "root")
    assert canonical_url("local://b", tmp_path / "root") == "local://local/b"
    (tmp_path / "root" / "b" / "x.f90").write_text("program x\nend program x\n")
    first = fetch("local://b", tmp_path / "repos", local_root=tmp_path / "root", max_bytes=10_000,
                  max_files=10, timeout_s=5)
    (tmp_path / "root" / "b" / "x.f90").write_text("program y\nend program y\n")
    second = fetch("local://b", tmp_path / "repos", local_root=tmp_path / "root", max_bytes=10_000,
                   max_files=10, timeout_s=5)
    assert first.commit != second.commit and len(first.commit) == 40 and first.path.is_dir()


def test_observed_schema_from_real_outputs():
    from replic8.contracts import observed_schema
    schema = observed_schema([
        {"found": "Y", "qty": 1, "items": [{"carrier": "A", "cost": 840.0}]},
        {"found": "N", "qty": 2.5, "items": []},
    ])
    assert schema["required"] == ["found", "items", "qty"]
    assert schema["properties"]["qty"] == {"type": "number"}
    assert schema["properties"]["items"]["items"]["properties"]["cost"] == {"type": "number"}


def test_learned_schema_replaces_the_guess():
    op = make_op().model_copy(update={"output_schema": {"type": "object", "required": ["wrong"]}})
    run = run_contract(Exec(), op, "u", COMMIT, [{"id": "1"}], learn_schema=True)
    assert run.result.passed and run.output_schema["required"] == ["id"]


def test_operator_examples_loosen_model_value_rules():
    from replic8.pipeline import fit_input_schema
    schema = {"type": "object", "additionalProperties": False, "required": ["part_id"],
              "properties": {"part_id": {"type": "string", "pattern": "^[A-Za-z0-9]+$", "maxLength": 8}}}
    fitted = fit_input_schema(schema, [{"part_id": "PMP-2210"}])
    assert fitted["properties"]["part_id"] == {"type": "string", "maxLength": 8}
    assert schema["properties"]["part_id"]["pattern"]  # original untouched
    assert fit_input_schema(schema, [{"part_id": 2210}]) is None          # wrong type
    assert fit_input_schema(schema, [{"partId": "PMP-2210"}]) is None     # wrong field name
    assert fit_input_schema(schema, []) == schema
