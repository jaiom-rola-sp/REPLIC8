"""Workspaces: token-opened, separate spaces on one gateway."""

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from replic8.config import SandboxLimits, Settings
from replic8.established import Catalog, EstablishedImporter
from replic8.events import EventLog
from replic8.gateway import create_app
from replic8.registry import Registry
from replic8.workspaces import Tenant, WorkspaceStore, WorkspaceValidator

from conftest import ALL_SCOPES, COMMIT, TOKEN, make_op, passed

ADMIN = "a" * 40
URL = "https://github.com/acme/legacy.git"
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}


class Exec:
    def call(self, op, version, payload):
        return {"id": payload["id"]}


def make_app(data_dir: Path, pipeline_for=None):
    settings = Settings(data_dir=data_dir, gateway_tokens=frozenset({TOKEN}), admin_tokens=frozenset({ADMIN}),
                        token_scopes=ALL_SCOPES)
    registry = Registry(data_dir)
    store = WorkspaceStore(data_dir)

    def build(workspace_id, folder):
        reg, ev, cat = Registry(folder), EventLog(folder), Catalog(folder)
        return Tenant(id=workspace_id, registry=reg, events=ev,
                      validator=WorkspaceValidator(settings, reg, workspace_id, store), catalog=cat,
                      importer=EstablishedImporter(settings, cat, reg, ev),
                      pipeline=pipeline_for(settings, reg, ev) if pipeline_for else None, is_workspace=True)

    app = create_app(settings, registry, Exec(), workspaces=store, build_workspace=build)
    return app, registry, store


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def tools(client, token):
    return [o["tool"] for o in client.get("/v1/operations", headers=auth(token)).json()["operations"]]


def test_only_the_admin_token_creates_workspaces(data_dir):
    app, _, _ = make_app(data_dir)
    c = TestClient(app)
    assert c.post("/v1/workspaces", headers=auth(TOKEN)).status_code == 401
    created = c.post("/v1/workspaces", json={"name": "Aryan demo"}, headers=auth(ADMIN))
    assert created.status_code == 201
    ws_token = created.json()["token"]
    assert ws_token.startswith("r8w_") and created.json()["name"] == "Aryan demo"
    # A workspace token can't create more workspaces.
    assert c.post("/v1/workspaces", headers=auth(ws_token)).status_code == 403


def test_workspace_creation_is_off_without_a_store(data_dir):
    settings = Settings(data_dir=data_dir, gateway_tokens=frozenset({TOKEN}), admin_tokens=frozenset({ADMIN}))
    c = TestClient(create_app(settings, Registry(data_dir), Exec()))
    assert c.post("/v1/workspaces", headers=auth(ADMIN)).status_code == 503


def test_tokens_are_stored_only_as_hashes(data_dir):
    _, _, store = make_app(data_dir)
    workspace_id, token = store.create("x")
    meta = (store.dir(workspace_id) / "workspace.json").read_text()
    assert token not in meta and json.loads(meta)["token_sha256"]
    assert WorkspaceStore(data_dir).resolve(token) == workspace_id  # survives a restart
    assert store.resolve("r8w_not-a-real-token") is None and store.resolve(TOKEN) is None


def test_each_token_sees_only_its_own_space(data_dir):
    app, default_registry, store = make_app(data_dir)
    c = TestClient(app, base_url="http://127.0.0.1:8000")
    one = c.post("/v1/workspaces", headers=auth(ADMIN)).json()
    two = c.post("/v1/workspaces", headers=auth(ADMIN)).json()
    default_registry.publish("maintenance", URL, COMMIT, [make_op()], {"maintenance.get_request": passed()})
    Registry(store.dir(one["id"])).publish("inventory", URL, COMMIT, [make_op("check_stock", ns="inventory")],
                                          {"inventory.check_stock": passed()})

    assert tools(c, TOKEN) == ["maintenance.get_request"]
    assert tools(c, one["token"]) == ["inventory.check_stock"]
    assert tools(c, two["token"]) == []  # a new workspace is blank

    # Calls are confined too.
    assert c.post("/v1/operations/inventory.check_stock", json={"input": {"id": "1"}},
                  headers=auth(one["token"])).status_code == 200
    assert c.post("/v1/operations/maintenance.get_request", json={"input": {"id": "1"}},
                  headers=auth(one["token"])).status_code == 404
    assert c.post("/v1/operations/inventory.check_stock", json={"input": {"id": "1"}},
                  headers=auth(two["token"])).status_code == 404

    # The workspace owner may run admin actions in its own space: the token is accepted (not 401/403);
    # this light setup has no pipeline, so the route answers 503.
    assert c.post("/v1/admin/systems/maintenance/check", headers=auth(one["token"])).status_code == 503
    assert c.get("/v1/workspace", headers=auth(one["token"])).json()["id"] == one["id"]
    assert c.get("/v1/workspace", headers=auth(TOKEN)).json()["kind"] == "default"

    # MCP follows the token as well.
    with c:
        listed = c.post("/mcp", headers={**auth(one["token"]), **MCP_HEADERS},
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()
        assert [t["name"] for t in listed["result"]["tools"]] == ["inventory.check_stock"]


def test_bad_and_deleted_workspace_tokens_are_refused(data_dir):
    app, _, _ = make_app(data_dir)
    c = TestClient(app)
    ws = c.post("/v1/workspaces", headers=auth(ADMIN)).json()
    assert c.get("/v1/operations", headers=auth("r8w_guess")).status_code == 401
    assert c.delete(f"/v1/workspaces/{ws['id']}", headers=auth(ws["token"])).status_code == 403
    assert c.delete(f"/v1/workspaces/{ws['id']}", headers=auth(ADMIN)).json() == {"deleted": ws["id"]}
    assert c.get("/v1/operations", headers=auth(ws["token"])).status_code == 401
    assert c.delete("/v1/workspaces/../etc", headers=auth(ADMIN)).status_code in (404, 405)


def test_event_history_survives_a_restart(tmp_path):
    first = EventLog(tmp_path)
    first.add("onboarded", system="maintenance", version=1)
    first.add("published", system="maintenance", version=1, operations=2)
    again = EventLog(tmp_path)
    assert [e["kind"] for e in again.since(0)] == ["onboarded", "published"]
    assert again.add("rolled_back", system="maintenance", version=1)["id"] == 3


# ---------- the real flow: import into a workspace, leave, restart, reopen ----------

ROOT = Path(__file__).resolve().parents[2]


def _image_ready() -> bool:
    from replic8.runtimes import LEGACY_IMAGE
    return bool(shutil.which("docker")) and subprocess.run(
        ["docker", "image", "inspect", LEGACY_IMAGE], capture_output=True).returncode == 0


@pytest.mark.skipif(not _image_ready(), reason="needs Docker with the legacy runtime image built")
def test_workspace_work_comes_back_after_leaving_and_restarting(tmp_path):
    from replic8.executor import Executor
    from replic8.pipeline import Pipeline
    from replic8.runtimes import pin_local_image
    from replic8.sandbox import Sandbox
    from test_pipeline import ScriptedModel

    local = tmp_path / "local"
    shutil.copytree(ROOT / "legacy" / "b-maintenance-cobol", local / "b-maint")
    data = tmp_path / "data"
    settings = Settings(data_dir=data, gateway_tokens=frozenset({TOKEN}), admin_tokens=frozenset({ADMIN}),
                        token_scopes=ALL_SCOPES, local_repo_root=local)
    sandbox = Sandbox(data / "repos", frozenset({pin_local_image()}), SandboxLimits(timeout_s=20),
                      builds_root=data / "builds")
    executor = Executor(sandbox, data / "repos")
    model = ScriptedModel(local)

    def start():
        registry, store = Registry(data), WorkspaceStore(data)

        def build(workspace_id, folder):
            reg, ev, cat = Registry(folder), EventLog(folder), Catalog(folder)
            return Tenant(id=workspace_id, registry=reg, events=ev,
                          validator=WorkspaceValidator(settings, reg, workspace_id, store), catalog=cat,
                          importer=EstablishedImporter(settings, cat, reg, ev),
                          pipeline=Pipeline(settings, reg, sandbox, executor, model, ev), is_workspace=True)

        app = create_app(settings, registry, executor, workspaces=store, build_workspace=build,
                         pipeline=Pipeline(settings, registry, sandbox, executor, model, EventLog(data)))
        return TestClient(app, base_url="http://127.0.0.1:8000")

    c = start()
    ws = c.post("/v1/workspaces", json={"name": "demo"}, headers=auth(ADMIN)).json()
    c.post("/v1/admin/systems", headers=auth(ws["token"]), json={
        "system": "maintenance", "repo_url": "local://b-maint",
        "examples": {"get_request": [{"request_id": "R-1001"}]}})
    end = time.time() + 90
    while time.time() < end and "maintenance.get_request" not in tools(c, ws["token"]):
        time.sleep(0.5)
    assert sorted(tools(c, ws["token"])) == ["maintenance.get_request", "maintenance.list_open_requests"]
    assert tools(c, TOKEN) == []  # the default space never saw it

    # "Leave", restart the backend, and reopen with the saved token.
    del c
    c = start()
    assert sorted(tools(c, ws["token"])) == ["maintenance.get_request", "maintenance.list_open_requests"]
    kinds = [e["kind"] for e in c.get("/v1/events", headers=auth(ws["token"])).json()["events"]]
    assert "published" in kinds
    answer = c.post("/v1/operations/maintenance.get_request", json={"input": {"request_id": "R-1001"}},
                    headers=auth(ws["token"])).json()
    assert answer["result"]["part_id"] == "PMP-2210"
