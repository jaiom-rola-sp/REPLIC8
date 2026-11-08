"""How a repo is read: functions, command-line programs, or both."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from replic8.config import SandboxLimits, Settings, token_id
from replic8.events import EventLog
from replic8.executor import Executor
from replic8.guard import MAX_OPERATIONS, Symbol, validate_proposal
from replic8.models import Tier, WrapperVersion
from replic8.pipeline import Pipeline, PipelineError
from replic8.registry import Registry
from replic8.runtimes import LEGACY_IMAGE, argv_for, pin_local_image
from replic8.sandbox import Sandbox

from conftest import TOKEN

LANGS = Path(__file__).parent / "fixtures" / "langs"
docker = pytest.mark.skipif(
    not shutil.which("docker")
    or subprocess.run(["docker", "image", "inspect", LEGACY_IMAGE], capture_output=True).returncode != 0,
    reason=f"needs Docker with {LEGACY_IMAGE} built")


class Recorder:
    def __init__(self):
        self.prompts = []

    def complete_json(self, system, user, schema=None):
        self.prompts.append(user)
        raise RuntimeError("stop after the prompt")  # these tests only look at what the model was shown


def world(tmp_path, folder):
    local = tmp_path / "local"
    shutil.copytree(LANGS / folder, local / "repo")
    data = tmp_path / "data"
    settings = Settings(data_dir=data, gateway_tokens=frozenset({TOKEN}), admin_tokens=frozenset({"a" * 40}),
                        token_scopes={token_id(TOKEN): frozenset({"x.*"})}, local_repo_root=local)
    sandbox = Sandbox(data / "repos", frozenset({pin_local_image()}), SandboxLimits(timeout_s=20), builds_root=data / "builds")
    model = Recorder()
    return Pipeline(settings, Registry(data), sandbox, Executor(sandbox, data / "repos"), model, EventLog(data)), model


def read_as(pipeline):
    return [e["detail"] for e in pipeline.events.since(0, 500) if e["kind"] == "mode_detected"]


@docker
@pytest.mark.parametrize("mode, expect, shown", [
    ("auto", "1 functions, 1 programs: reading as functions and programs", ("price(sku)", "tool (program)")),
    ("functions", "1 functions, 0 programs: reading as functions (mode: functions)", ("price(sku)",)),
    ("programs", "0 functions, 1 programs: reading as programs (mode: programs)", ("tool (program)",)),
])
def test_what_the_model_is_shown_follows_the_mode(tmp_path, mode, expect, shown):
    p, model = world(tmp_path, "py_mixed")
    with pytest.raises(PipelineError):
        p.onboard("x", "local://repo", mode=mode)
    assert read_as(p) == [expect]
    prompt = model.prompts[0].split("Source files:")[0]  # the listing; the source text itself is always sent
    assert all(s in prompt for s in shown)
    assert ("tool (program)" in prompt) == (mode != "functions") and ("price(sku)" in prompt) == (mode != "programs")


@docker
def test_a_mode_with_nothing_to_wrap_says_what_the_repo_has(tmp_path):
    p, _ = world(tmp_path, "py_library")
    with pytest.raises(PipelineError, match="no command-line programs found.*it has"):
        p.onboard("x", "local://repo", mode="programs")
    p2, _ = world(tmp_path / "b", "cli_perl")
    with pytest.raises(PipelineError, match="no callable functions found.*command-line programs"):
        p2.onboard("x", "local://repo", mode="functions")
    with pytest.raises(PipelineError, match="mode must be"):
        p2.onboard("x", "local://repo", mode="everything")


def test_old_versions_without_a_mode_still_load():
    raw = {"system": "x", "version": 1, "source_commit": "a" * 40, "repo_url": "https://github.com/o/r",
           "operations": [], "tests": {}}
    assert WrapperVersion.model_validate(raw).mode == "auto"


def test_functions_and_programs_share_the_operation_limit(tmp_path):
    (tmp_path / "a.py").write_text("\n" * 60)
    funcs = [Symbol(f"f{i}", "a.py", 1 + i) for i in range(7)]
    progs = [Symbol(f"p{i}", "a.py", 20 + i, program=True) for i in range(13)]

    def item(sym):
        op = {"name": sym.name, "symbol": sym.name, "file": "a.py", "line": sym.line, "access": "read", "description": "d",
              "input_schema": {"type": "object", "properties": {}, "required": []}, "output_schema": {"type": "object"}}
        if sym.program:
            op["cli"] = {"args": ["x"], "output": "lines"}
        return op

    raw = json.dumps({"operations": [item(s) for s in progs + funcs]})
    accepted, rejected = validate_proposal(raw, namespace="x", tier=Tier.parsed, repo_root=tmp_path,
                                           image=LEGACY_IMAGE, argv_for=argv_for, symbols=funcs + progs)
    assert len(accepted) == 17 and sorted(rejected) == ["x.p10", "x.p11", "x.p12"]
    assert all("share" in why for why in rejected.values())
