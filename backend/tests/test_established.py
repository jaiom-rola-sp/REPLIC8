"""Established systems (FR-15): read the OpenAPI file, list operations, show in the graph, never call."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from conftest import COMMIT, TOKEN, make_op, passed
from replic8.config import Settings, token_id
from replic8.established import Catalog, EstablishedError, EstablishedImporter
from replic8.events import EventLog
from replic8.gateway import create_app
from replic8.graph import build_graph
from replic8.openapi_spec import SpecError, find_spec, load_spec, read_operations
from replic8.registry import Registry

ADMIN = "a" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}
ADMIN_AUTH = {"Authorization": f"Bearer {ADMIN}"}

PARENT_YAML = """
openapi: 3.0.3
info: {title: Company A platform, version: 2.1.0}
paths:
  /parts/{part_id}:
    parameters:
      - {name: part_id, in: path, required: true, schema: {type: string}}
    get:
      operationId: getPartForecast
      summary: Forecast demand for a part
      responses:
        200:
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Forecast'}
  /work-orders:
    get:
      summary: List open work orders
      parameters:
        - {$ref: '#/components/parameters/Site'}
      responses:
        '200':
          content:
            application/json:
              schema: {type: array, items: {$ref: '#/components/schemas/WorkOrder'}}
    post:
      operationId: createWorkOrder
      requestBody:
        content:
          application/json:
            schema: {$ref: '#/components/schemas/WorkOrder'}
      responses: {'201': {description: created}}
components:
  parameters:
    Site: {name: site_region, in: query, schema: {type: string}}
  schemas:
    Forecast:
      allOf:
        - {$ref: '#/components/schemas/PartRef'}
        - {type: object, properties: {units: {type: integer}}}
    PartRef: {type: object, properties: {part_id: {type: string}}, required: [part_id]}
    WorkOrder:
      type: object
      properties:
        request_id: {type: string}
        part_id: {type: string}
        next: {$ref: '#/components/schemas/WorkOrder'}
"""

SWAGGER_JSON = {
    "swagger": "2.0", "info": {"title": "Old but modern", "version": "1"},
    "paths": {"/stock": {"get": {
        "operationId": "get-stock",
        "parameters": [{"name": "part_id", "in": "query", "type": "string", "required": True}],
        "responses": {"200": {"schema": {"type": "object", "properties": {"on_hand": {"type": "integer"}}}}}}}},
}


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def ops_by_name(path):
    return {op["name"]: op for op in read_operations(load_spec(path))}


# ---------- reading the file ----------

def test_reads_openapi3_yaml_with_refs_allof_and_cycles(tmp_path):
    ops = ops_by_name(write(tmp_path, "openapi.yaml", PARENT_YAML))
    assert set(ops) == {"get_part_forecast", "get_work_orders", "create_work_order"}
    forecast = ops["get_part_forecast"]
    assert (forecast["method"], forecast["path"]) == ("GET", "/parts/{part_id}")
    assert forecast["input_schema"]["required"] == ["part_id"]
    assert set(forecast["output_schema"]["properties"]) == {"part_id", "units"}     # allOf merged
    assert ops["get_work_orders"]["input_schema"]["properties"]["site_region"] == {"type": "string"}
    assert ops["get_work_orders"]["output_schema"]["type"] == "array"
    body = ops["create_work_order"]["input_schema"]["properties"]
    assert {"request_id", "part_id"} <= set(body)                                     # body fields lifted
    assert body["next"] == {}                                                         # cycle cut


def test_reads_swagger2_json(tmp_path):
    ops = ops_by_name(write(tmp_path, "swagger.json", json.dumps(SWAGGER_JSON)))
    assert ops["get_stock"]["input_schema"]["properties"]["part_id"]["type"] == "string"
    assert ops["get_stock"]["output_schema"]["properties"]["on_hand"] == {"type": "integer"}


def test_yaml_aliases_are_refused(tmp_path):
    bomb = "openapi: 3.0.0\npaths: {}\na: &a [x, x]\nb: &b [*a, *a]\n"
    with pytest.raises(SpecError, match="aliases"):
        load_spec(write(tmp_path, "openapi.yaml", bomb))


@pytest.mark.parametrize("text", ["not: [valid", "openapi: 1.0\npaths: {}", "- a list", "openapi: 3.1.0\n"])
def test_bad_files_get_a_plain_error(tmp_path, text):
    with pytest.raises(SpecError):
        load_spec(write(tmp_path, "openapi.yaml", text))


def test_finds_the_shallowest_known_file_and_skips_vendor(tmp_path):
    write(tmp_path, "node_modules/pkg/openapi.yaml", PARENT_YAML)
    write(tmp_path, "docs/api/swagger.json", "{}")
    write(tmp_path, "api/openapi.yaml", PARENT_YAML)
    assert find_spec(tmp_path).relative_to(tmp_path).as_posix() == "api/openapi.yaml"
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SpecError, match="no OpenAPI file"):
        find_spec(empty)


@pytest.mark.parametrize("given", ["../outside.yaml", "/etc/passwd.yaml", "spec/api.txt", "a\\b.yaml", "missing.yaml"])
def test_a_given_path_must_stay_inside_the_repo(tmp_path, given):
    repo = tmp_path / "repo"
    write(repo, "spec/api.txt", "x")
    write(tmp_path, "outside.yaml", PARENT_YAML)
    with pytest.raises(SpecError):
        find_spec(repo, given)


def test_operation_names_are_safe_and_unique(tmp_path):
    spec = {"openapi": "3.0.0", "paths": {
        "/a": {"get": {"operationId": "9 Lives!"}, "put": {"operationId": "9 Lives!"}},
        "/b/{id}": {"delete": {}}}}
    ops = read_operations(spec)
    assert [o["name"] for o in ops] == ["op_9_lives", "op_9_lives_2", "delete_b_id"]


def test_too_many_operations_is_refused(monkeypatch):
    from replic8 import openapi_spec
    monkeypatch.setattr(openapi_spec, "MAX_OPERATIONS", 3)
    spec = {"openapi": "3.0.0", "paths": {f"/p{i}": {"get": {}} for i in range(4)}}
    with pytest.raises(SpecError, match="more than 3"):
        read_operations(spec)


# ---------- importing, storing, the gateway ----------

@pytest.fixture
def world(tmp_path):
    repos = tmp_path / "repos"
    write(repos / "company-a", "openapi.yaml", PARENT_YAML)
    write(repos / "no-spec", "README.md", "nothing here")
    data = tmp_path / "data"
    reg = Registry(data)
    inventory = make_op("check_stock", ns="inventory")
    inventory.input_schema["properties"] = {"part_id": {"type": "string"}}
    inventory.output_schema["properties"] = {"part_id": {"type": "string"}, "on_hand": {"type": "integer"}}
    reg.publish("inventory", "https://github.com/acme/inv", COMMIT, [inventory], {"inventory.check_stock": passed()})
    settings = Settings(data_dir=data, gateway_tokens=frozenset({TOKEN}), admin_tokens=frozenset({ADMIN}),
                        token_scopes={token_id(TOKEN): frozenset({"inventory.*", "company_a.*"})},
                        local_repo_root=repos)
    events = EventLog()
    catalog = Catalog(data)
    client = TestClient(create_app(settings, reg, executor=None, events=events, catalog=catalog))
    return client, settings, reg, catalog, events


def importer(world):
    _, settings, reg, catalog, events = world
    return EstablishedImporter(settings, catalog, reg, events)


def test_import_lists_operations_and_logs_progress(world):
    entry = importer(world).run("company_a", "local://company-a", parent=True)
    assert entry.parent and entry.spec_file == "openapi.yaml" and entry.title == "Company A platform"
    assert len(entry.operations) == 3
    kinds = [(e["kind"], e["detail"]) for e in world[4].since(0)]
    assert kinds == [("onboard_started", "established"), ("onboard_stage", "fetch"), ("onboard_stage", "read"),
                     ("onboard_stage", "list"), ("listed", "established")]
    assert world[4].since(0)[-1]["operations"] == 3


def test_reimport_replaces_the_entry(world):
    imp = importer(world)
    imp.run("company_a", "local://company-a", parent=True)
    imp.run("company_a", "local://company-a", parent=False)
    assert world[3].systems() == ["company_a"] and world[3].get("company_a").parent is False


def test_import_failures_are_reported(world):
    with pytest.raises(EstablishedError, match="no OpenAPI file"):
        importer(world).run("nothing", "local://no-spec")
    assert world[4].since(0)[-1]["kind"] == "onboard_failed"
    with pytest.raises(EstablishedError, match="legacy system"):
        importer(world).run("inventory", "local://company-a")
    assert world[3].systems() == []


def test_established_tools_can_never_be_called(world):
    client = world[0]
    importer(world).run("company_a", "local://company-a", parent=True)
    r = client.post("/v1/operations/company_a.get_part_forecast", json={"input": {"part_id": "PMP-2210"}}, headers=AUTH)
    assert r.status_code == 404
    tools = [o["tool"] for o in client.get("/v1/operations", headers=AUTH).json()["operations"]]
    assert tools == ["inventory.check_stock"]
    assert not any(p.startswith("/v1/operations/company_a") for p in client.get("/v1/openapi.json", headers=AUTH).json()["paths"])


def test_established_listing_and_graph(world):
    client = world[0]
    importer(world).run("company_a", "local://company-a", parent=True)
    listed = client.get("/v1/established", headers=AUTH).json()["systems"]
    assert listed[0]["system"] == "company_a" and listed[0]["called_by_replic8"] is False
    assert {o["tool"] for o in listed[0]["operations"]} >= {"company_a.get_part_forecast"}

    graph = client.get("/v1/graph", headers=AUTH).json()
    node = next(n for n in graph["nodes"] if n["id"] == "system:company_a")
    assert node["kind"] == "established" and node["parent"] is True
    assert {"id": "company_a->gateway", "source": "system:company_a", "target": "gateway", "type": "uses"} in graph["edges"]
    pairs = {(l["source"], l["target"]): l["fields"] for l in graph["system_links"]}
    assert pairs[("company_a", "inventory")] == ["part_id"]      # Company A's forecast returns part_id
    assert pairs[("inventory", "company_a")] == ["part_id"]


def test_only_the_parent_gets_the_line_into_the_gateway(world):
    importer(world).run("company_a", "local://company-a", parent=False)
    graph = build_graph(world[2], catalog=world[3])
    assert not [e for e in graph["edges"] if e["type"] == "uses"]


def test_admin_route_runs_in_the_background(world):
    client = world[0]
    assert client.post("/v1/admin/established", json={"system": "company_a", "repo_url": "local://company-a"},
                       headers=AUTH).status_code == 401
    r = client.post("/v1/admin/established", json={"system": "company_a", "repo_url": "local://company-a",
                                                   "parent": True}, headers=ADMIN_AUTH)
    assert r.status_code == 202
    for _ in range(100):
        if world[3].get("company_a"):
            break
        time.sleep(0.05)
    assert world[3].get("company_a").parent is True


@pytest.mark.parametrize("body,status", [
    ({"system": "company_a", "repo_url": "https://gitlab.com/a/b"}, 422),
    ({"system": "company_a", "repo_url": "local://company-a", "spec_path": "../x.yaml"}, 202),  # refused later, in events
    ({"system": "company_a", "repo_url": "local://company-a", "spec_path": "a b.yaml"}, 422),
    ({"system": "inventory", "repo_url": "local://company-a"}, 409),
])
def test_admin_route_checks_input(world, body, status):
    assert world[0].post("/v1/admin/established", json=body, headers=ADMIN_AUTH).status_code == status


class IdlePipeline:
    def __init__(self, events):
        self.events = events
        self.started = []

    def busy(self, system):
        return False

    def onboard(self, *args):
        self.started.append(args)


def test_legacy_onboarding_refuses_an_established_name(world):
    _, settings, reg, catalog, events = world
    importer(world).run("company_a", "local://company-a")
    pipeline = IdlePipeline(events)
    client = TestClient(create_app(settings, reg, executor=None, pipeline=pipeline, catalog=catalog))
    r = client.post("/v1/admin/systems", json={"system": "company_a", "repo_url": "local://company-a"}, headers=ADMIN_AUTH)
    assert r.status_code == 409 and pipeline.started == []
