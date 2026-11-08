"""A command-line program end to end: found, shown to the model with its --help, published as black-box, called."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from replic8.config import SandboxLimits, Settings, token_id
from replic8.events import EventLog
from replic8.executor import Executor
from replic8.gateway import create_app
from replic8.pipeline import Pipeline
from replic8.registry import Registry
from replic8.runtimes import LEGACY_IMAGE, pin_local_image
from replic8.sandbox import Sandbox

from conftest import TOKEN

LANGS = Path(__file__).parent / "fixtures" / "langs"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

pytestmark = pytest.mark.skipif(
    not shutil.which("docker")
    or subprocess.run(["docker", "image", "inspect", LEGACY_IMAGE], capture_output=True).returncode != 0,
    reason=f"needs Docker with {LEGACY_IMAGE} built")


class ScriptedModel:
    def __init__(self, ops):
        self.ops, self.prompts = ops, []

    def complete_json(self, system, user, schema=None):
        self.prompts.append(user)
        return json.dumps({"operations": self.ops})


def lookup_op(**over):
    op = {"name": "get_stock", "symbol": "lookup", "file": "lookup.pl", "line": 4, "access": "read",
          "description": "on hand for a part",
          "input_schema": {"type": "object", "properties": {"part_id": {"type": "string", "maxLength": 20}},
                           "required": ["part_id"], "additionalProperties": False},
          "output_schema": {"type": "object", "required": ["on_hand"]},
          "examples": [{"part_id": "P-1"}], "cli": {"args": ["{part_id}"], "output": "keyvalue"}}
    op.update(over)
    return op


def onboard(tmp_path, ops):
    local = tmp_path / "local"
    shutil.copytree(LANGS / "cli_perl", local / "stock-cli")
    data = tmp_path / "data"
    settings = Settings(data_dir=data, gateway_tokens=frozenset({TOKEN}), admin_tokens=frozenset({"a" * 40}),
                        token_scopes={token_id(TOKEN): frozenset({"stock.*"})}, local_repo_root=local)
    sandbox = Sandbox(data / "repos", frozenset({pin_local_image()}), SandboxLimits(timeout_s=20), builds_root=data / "builds")
    registry, model = Registry(data), ScriptedModel(ops)
    pipeline = Pipeline(settings, registry, sandbox, Executor(sandbox, data / "repos"), model, EventLog(data), heal_cooldown_s=0)
    version = pipeline.onboard("stock", "local://stock-cli")
    return version, model, create_app(settings, registry, pipeline.executor, pipeline=pipeline)


def test_program_is_published_as_black_box_and_called(tmp_path):
    version, model, app = onboard(tmp_path, [lookup_op()])
    assert [(o.name, o.tier.value) for o in version.operations] == [("get_stock", "black-box")], version.rejected
    assert "lookup (program) at lookup.pl:4" in model.prompts[0] and "--help printed (untrusted)" in model.prompts[0]
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        r = c.post("/v1/operations/stock.get_stock", json={"input": {"part_id": "P-7"}}, headers=AUTH)
        assert r.json()["result"]["on_hand"] == 12 and r.json()["provenance"]["tier"] == "black-box"
        assert c.post("/v1/operations/stock.get_stock", json={"input": {"part_id": "--help"}}, headers=AUTH).status_code == 422


def test_guard_rejections_through_the_pipeline(tmp_path):
    bad = [lookup_op(name="shell", cli={"args": ["{part_id}", "; id"], "output": "json"}),
           lookup_op(name="no_form", cli=None),
           lookup_op(name="wrong_file", file="nope.pl")]
    bad[1].pop("cli")
    ops = [lookup_op(), *bad]
    version, _, _ = onboard(tmp_path, ops)
    assert [o.name for o in version.operations] == ["get_stock"]
    assert {"stock.shell", "stock.no_form", "stock.wrong_file"} <= set(version.rejected)
