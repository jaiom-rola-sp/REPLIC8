"""Full lifecycle on the real COBOL and Java demo systems, with a scripted model.

onboard B and C -> contract tests -> graph edge from real fields -> call through
REST and MCP -> rename GET-REQUEST in the COBOL -> call fails -> trigger_heal ->
repair replays the recorded contract -> v2 saved -> same answer -> rollback.
"""

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from replic8.config import SandboxLimits, Settings
from replic8.events import EventLog
from replic8.executor import Executor
from replic8.extract import extract_symbols
from replic8.gateway import create_app
from replic8.pipeline import Pipeline, PipelineError
from replic8.registry import Registry
from replic8.runtimes import LEGACY_IMAGE, callable_symbols
from replic8.sandbox import Sandbox

from conftest import TOKEN

ROOT = Path(__file__).resolve().parents[2]
ADMIN = "a" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}
ADMIN_AUTH = {"Authorization": f"Bearer {ADMIN}"}

pytestmark = pytest.mark.skipif(
    not shutil.which("docker")
    or subprocess.run(["docker", "image", "inspect", LEGACY_IMAGE], capture_output=True).returncode != 0,
    reason=f"needs Docker with {LEGACY_IMAGE} built",
)


class ScriptedModel:
    """Stands in for Nemotron: answers from the real extracted symbols, like the live model did."""

    def __init__(self, local_root: Path):
        self.root = local_root
        self.calls = []

    def _sym(self, folder, name):
        syms = {s.name: s for s in callable_symbols(self.root / folder, extract_symbols(self.root / folder)[0])}
        return syms[name]

    def _op(self, folder, name, symbol, props, examples, required=("found",)):
        s = self._sym(folder, symbol)
        return {"name": name, "symbol": s.name, "file": s.file, "line": s.line, "access": "read",
                "description": name.replace("_", " "),
                "input_schema": {"type": "object", "properties": props, "required": list(props),
                                 "additionalProperties": False},
                "output_schema": {"type": "object", "required": list(required)}, "examples": examples}

    def complete_json(self, system, user, schema=None):
        self.calls.append(system)
        string = {"type": "string", "maxLength": 10}
        if "'maintenance'" in system:
            heal = "repair" in system
            ops = [self._op("b-maint", "get_request", "FETCH-REQUEST" if heal else "GET-REQUEST",
                            {"request_id": string}, [{"request_id": "R-9999"}])]
            if not heal:
                ops.append(self._op("b-maint", "list_open_requests", "LIST-OPEN-REQUESTS",
                                    {"well_id": string}, [{"well_id": "W-17"}], required=("count", "items")))
            return json.dumps({"operations": ops})
        return json.dumps({"operations": [
            self._op("c-inv", "check_stock", "checkStock", {"part_id": string}, [{"part_id": "PMP-2210"}]),
            self._op("c-inv", "get_shipping_options", "getShippingOptions",
                     {"part_id": string, "destination": string},
                     [{"part_id": "PMP-2210", "destination": "PERMIAN"}]),
        ]})


@pytest.fixture
def world(tmp_path):
    local = tmp_path / "local"
    shutil.copytree(ROOT / "legacy" / "b-maintenance-cobol", local / "b-maint")
    shutil.copytree(ROOT / "legacy" / "c-inventory-java", local / "c-inv")
    data = tmp_path / "data"
    settings = Settings(data_dir=data, gateway_tokens=frozenset({TOKEN}), admin_tokens=frozenset({ADMIN}),
                        local_repo_root=local)
    sandbox = Sandbox(data / "repos", frozenset({LEGACY_IMAGE}), SandboxLimits(timeout_s=20),
                      builds_root=data / "builds")
    executor = Executor(sandbox, data / "repos")
    registry = Registry(data)
    pipeline = Pipeline(settings, registry, sandbox, executor, ScriptedModel(local),
                        EventLog(data), heal_cooldown_s=0)
    app = create_app(settings, registry, executor, pipeline=pipeline)
    return {"local": local, "pipeline": pipeline, "registry": registry, "app": app}


def _wait_for(events, kind, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        found = [e for e in events.since(0, 500) if e["kind"] == kind]
        if found:
            return found[-1]
        time.sleep(0.5)
    raise AssertionError(f"no {kind} event; got {[e['kind'] for e in events.since(0, 500)]}")


def test_full_lifecycle(world):
    p, reg = world["pipeline"], world["registry"]

    # Onboard both systems. The operator supplies one known-good ID for B.
    b1 = p.onboard("maintenance", "local://b-maint", examples={"get_request": [{"request_id": "R-1001"}]})
    c1 = p.onboard("inventory", "local://c-inv")
    assert sorted(op.name for op in b1.operations) == ["get_request", "list_open_requests"], (b1.rejected, {k: t.detail for k, t in b1.tests.items()})
    assert sorted(op.name for op in c1.operations) == ["check_stock", "get_shipping_options"]
    recorded = {json.dumps(c.input): c.output for c in b1.cases["maintenance.get_request"]}
    assert recorded['{"request_id": "R-1001"}']["part_id"] == "PMP-2210"
    assert recorded['{"request_id": "R-9999"}']["found"] == "N"

    with TestClient(world["app"], base_url="http://127.0.0.1:8000") as client:
        # Graph: B's get_request returns part_id, which C's tools take as input (seen in real outputs).
        graph = client.get("/v1/graph", headers=AUTH).json()
        data_edges = {(e["source"], e["target"], e["field"], e["evidence"]) for e in graph["edges"] if e["type"] == "data"}
        assert ("maintenance.get_request", "inventory.check_stock", "part_id", "recorded") in data_edges

        # The demo flow through REST.
        req = client.post("/v1/operations/maintenance.get_request", json={"input": {"request_id": "R-1001"}},
                          headers=AUTH).json()["result"]
        stock = client.post("/v1/operations/inventory.check_stock", json={"input": {"part_id": req["part_id"]}},
                            headers=AUTH).json()["result"]
        assert stock["on_hand"] == 12

        # The same tool through MCP.
        mcp_headers = {**AUTH, "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
        call = client.post("/mcp", headers=mcp_headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": "inventory.get_shipping_options",
                                      "arguments": {"part_id": "PMP-2210", "destination": "PERMIAN"}}}).json()
        assert call["result"]["structuredContent"]["result"]["count"] == 2

        # The live break: rename the COBOL paragraph and its dispatch line in the legacy repo.
        src = world["local"] / "b-maint" / "src" / "MAINT.cbl"
        src.write_text(src.read_text().replace("GET-REQUEST", "FETCH-REQUEST"))
        # Agents are unaffected: v1 stays pinned to the commit it was tested on.
        still = client.post("/v1/operations/maintenance.get_request", json={"input": {"request_id": "R-1001"}},
                            headers=AUTH)
        assert still.status_code == 200 and still.json()["provenance"]["version"] == 1

        # Change detection (the scheduled poll calls the same thing) finds the new code and repairs it.
        assert client.post("/v1/admin/systems/maintenance/check", headers=AUTH).status_code == 401
        check = client.post("/v1/admin/systems/maintenance/check", headers=ADMIN_AUTH).json()
        assert check["change_detected"] is True
        saved = _wait_for(p.events, "heal_saved")
        assert saved["version"] == 2
        b2 = reg.current("maintenance")
        assert b2.reason.startswith("self-heal") and b2.parent_version == 1
        healed = {op.name: op for op in b2.operations}
        assert healed["get_request"].invocation.argv[-1] == "FETCH-REQUEST"
        assert healed["list_open_requests"].tool == "maintenance.list_open_requests"  # kept, relocated
        fixed = client.post("/v1/operations/maintenance.get_request", json={"input": {"request_id": "R-1001"}},
                            headers=AUTH).json()
        assert fixed["result"] == req and fixed["provenance"]["version"] == 2

        # History and rollback (admin only).
        versions = client.get("/v1/systems/maintenance/versions", headers=AUTH).json()
        assert [v["version"] for v in versions["versions"]] == [1, 2]
        assert client.post("/v1/admin/systems/maintenance/rollback", json={"version": 1}, headers=AUTH).status_code == 401
        assert client.post("/v1/admin/systems/maintenance/rollback", json={"version": 1},
                           headers=ADMIN_AUTH).json()["version"] == 1

        kinds = [e["kind"] for e in client.get("/v1/events", headers=AUTH).json()["events"]]
        failed = [e for e in client.get("/v1/events", headers=AUTH).json()["events"] if e["kind"] == "contract_failed"]
        assert failed and failed[0]["tool"] == "maintenance.get_request" and "FunctionMissing" in failed[0]["detail"]
        for kind in ("onboarded", "published", "change_detected", "heal_started", "heal_saved", "rolled_back"):
            assert kind in kinds



def test_repair_that_changes_answers_is_not_saved(world):
    p = world["pipeline"]
    p.onboard("maintenance", "local://b-maint", examples={"get_request": [{"request_id": "R-1001"}]})
    # Rename AND change the data the legacy program returns: replay must catch it.
    src = world["local"] / "b-maint" / "src" / "MAINT.cbl"
    src.write_text(src.read_text().replace("GET-REQUEST", "FETCH-REQUEST"))
    data = world["local"] / "b-maint" / "data" / "requests.dat"
    data.write_text(data.read_text().replace("PMP-2210  PERMIAN   001", "PMP-9999  PERMIAN   001"))
    outcome = p.heal("maintenance", reason="test")
    # Both operations now return different answers for their recorded inputs
    # (W-17's open list includes R-1001), so nothing is saved and v1 keeps serving.
    assert outcome.status == "failed"
    assert world["registry"].current("maintenance").version == 1
    failed = [e for e in p.events.since(0) if e["kind"] == "contract_failed"]
    assert {e["tool"] for e in failed} == {"maintenance.get_request", "maintenance.list_open_requests"}


def test_code_change_that_keeps_contracts_needs_no_model(world):
    p = world["pipeline"]
    p.onboard("inventory", "local://c-inv")
    calls = len(p.model.calls)
    src = world["local"] / "c-inv" / "src/com/subc/pil/Inventory.java"
    src.write_text("// harmless comment added by a maintainer\n" + src.read_text())
    outcome = p.heal("inventory")
    assert outcome.status == "saved" and len(p.model.calls) == calls
    assert world["registry"].current("inventory").reason == "code changed; contracts still pass"


def test_trigger_heal_only_for_prd_errors(world):
    from replic8.sandbox import FunctionMissing, SandboxTimeout
    p = world["pipeline"]
    p.onboard("inventory", "local://c-inv")
    assert p.trigger_heal("inventory.check_stock", SandboxTimeout()) is False
    assert p.trigger_heal("inventory.check_stock", FunctionMissing()) is True
    _wait_for(p.events, "heal_skipped")  # same code, so nothing to repair
    assert [e["kind"] for e in p.events.since(0) if e["kind"] == "call_failed"] == ["call_failed", "call_failed"]


def test_unchanged_code_is_not_healed(world):
    p = world["pipeline"]
    p.onboard("inventory", "local://c-inv")
    assert p.heal("inventory").status == "skipped"
    assert world["registry"].versions("inventory") == [1]


def test_onboarding_errors_are_safe(world):
    p = world["pipeline"]
    for url in ("local://../etc", "local://missing", "file:///etc/passwd", "https://evil.com/a/b"):
        with pytest.raises(PipelineError):
            p.onboard("maintenance", url)
    with pytest.raises(PipelineError):
        p.onboard("Bad Name", "local://b-maint")
