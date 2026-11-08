"""A Python repo end to end: onboard -> contract tests in the real sandbox -> publish -> call over REST."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from replic8.config import SandboxLimits, Settings, token_id
from replic8.events import EventLog
from replic8.executor import Executor
from replic8.extract import extract_symbols
from replic8.gateway import create_app
from replic8.pipeline import Pipeline
from replic8.registry import Registry
from replic8.runtimes import LEGACY_IMAGE, callable_symbols, pin_local_image
from replic8.sandbox import Sandbox

from conftest import TOKEN

FIXTURE = Path(__file__).parent / "fixtures" / "langs" / "py_library"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

pytestmark = pytest.mark.skipif(
    not shutil.which("docker")
    or subprocess.run(["docker", "image", "inspect", LEGACY_IMAGE], capture_output=True).returncode != 0,
    reason=f"needs Docker with {LEGACY_IMAGE} built",
)


class ScriptedModel:
    def __init__(self, root: Path):
        self.root = root

    def _op(self, name, symbol, props, required, examples, out_required):
        s = {x.name: x for x in callable_symbols(self.root, extract_symbols(self.root)[0])}[symbol]
        return {"name": name, "symbol": s.name, "file": s.file, "line": s.line, "access": "read",
                "description": name.replace("_", " "),
                "input_schema": {"type": "object", "properties": props, "required": required,
                                 "additionalProperties": False},
                "output_schema": {"type": "object", "required": out_required}, "examples": examples}

    def complete_json(self, system, user, schema=None):
        text = {"type": "string", "maxLength": 20}
        num = {"type": "number"}
        return json.dumps({"operations": [
            self._op("invoice_total", "invoice_total", {"quantity": num, "unit_price": num, "tax_rate": num},
                     ["quantity", "unit_price"], [{"quantity": 2, "unit_price": 10}], ["total"]),
            self._op("list_items", "list_items", {"customer": text}, ["customer"], [{"customer": "C-1"}], ["items"]),
            self._op("customer_name", "customer_name", {"customer_id": text}, ["customer_id"],
                     [{"customer_id": "C-1"}], ["result"]),
        ]})


def test_python_repo_end_to_end(tmp_path):
    local = tmp_path / "local"
    shutil.copytree(FIXTURE, local / "py-billing")
    data = tmp_path / "data"
    settings = Settings(data_dir=data, gateway_tokens=frozenset({TOKEN}), admin_tokens=frozenset({"a" * 40}),
                        token_scopes={token_id(TOKEN): frozenset({"billing.*"})}, local_repo_root=local)
    sandbox = Sandbox(data / "repos", frozenset({pin_local_image()}), SandboxLimits(timeout_s=20),
                      builds_root=data / "builds")
    registry = Registry(data)
    executor = Executor(sandbox, data / "repos")
    pipeline = Pipeline(settings, registry, sandbox, executor, ScriptedModel(local / "py-billing"),
                        EventLog(data), heal_cooldown_s=0)

    version = pipeline.onboard("billing", "local://py-billing")
    assert sorted(op.name for op in version.operations) == ["customer_name", "invoice_total", "list_items"], (
        version.rejected, {k: t.detail for k, t in version.tests.items()})

    with TestClient(create_app(settings, registry, executor, pipeline=pipeline), base_url="http://127.0.0.1:8000") as c:
        def call(tool, body):
            return c.post(f"/v1/operations/billing.{tool}", json={"input": body}, headers=AUTH)

        assert call("invoice_total", {"quantity": 2, "unit_price": 10}).json()["result"] == {"total": 22.0}
        assert call("list_items", {"customer": "C-1"}).json()["result"]["items"][0] == {"sku": "A1", "qty": 2}
        assert call("customer_name", {"customer_id": "C-1"}).json()["result"] == {"result": "ACME Corp"}
        assert call("invoice_total", {"quantity": 2}).status_code == 422  # unit_price is required
