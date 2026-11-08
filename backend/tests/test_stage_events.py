"""Onboarding reports which step it is on, so the dashboard can show where an import stopped.

No Docker needed: the imports below stop before the sandbox is used.
"""

import pytest

from replic8.config import SandboxLimits, Settings
from replic8.events import EventLog
from replic8.executor import Executor
from replic8.pipeline import Pipeline, PipelineError
from replic8.registry import Registry
from replic8.sandbox import Sandbox


@pytest.fixture
def world(tmp_path):
    local = tmp_path / "local"
    (local / "python-only").mkdir(parents=True)
    (local / "python-only" / "app.py").write_text("print('hi')\n")
    data = tmp_path / "data"
    settings = Settings(data_dir=data, local_repo_root=local)
    sandbox = Sandbox(data / "repos", frozenset(), SandboxLimits(), builds_root=data / "builds")
    events = EventLog()
    pipeline = Pipeline(settings, Registry(data), sandbox, Executor(sandbox, data / "repos"), None, events)
    return pipeline, events


def _run(pipeline, events):
    with pytest.raises(PipelineError) as err:
        pipeline.onboard("demo", "local://python-only")
    kinds = [(e["kind"], e["detail"]) for e in events.since(0, 50)]
    return str(err.value), kinds


def test_stages_are_reported_in_order_until_the_failing_step(world):
    pipeline, events = world
    message, kinds = _run(pipeline, events)
    assert [d for k, d in kinds if k == "onboard_stage"] == ["fetch", "detect"]
    assert kinds[0] == ("onboard_started", "")
    assert kinds[-1][0] == "onboard_failed" and "no supported language" in kinds[-1][1]
    assert "no supported language" in message


def test_stage_events_carry_only_the_system_and_a_fixed_stage_name(world):
    pipeline, events = world
    _run(pipeline, events)
    stage = next(e for e in events.since(0, 50) if e["kind"] == "onboard_stage")
    assert stage["system"] == "demo" and stage["detail"] == "fetch"


# ---- failures must always reach the dashboard ----

def _cobol_repo(world_dir):
    (world_dir / "cobol-app").mkdir(parents=True)
    (world_dir / "cobol-app" / "MAIN.cbl").write_text("       IDENTIFICATION DIVISION.\n")


@pytest.fixture
def cobol_world(tmp_path):
    local = tmp_path / "local"
    _cobol_repo(local)
    data = tmp_path / "data"
    settings = Settings(data_dir=data, local_repo_root=local)
    sandbox = Sandbox(data / "repos", frozenset(), SandboxLimits(), builds_root=data / "builds")
    events = EventLog()
    return Pipeline(settings, Registry(data), sandbox, Executor(sandbox, data / "repos"), None, events), events, sandbox


def test_missing_docker_is_reported_as_a_clear_failure(cobol_world, monkeypatch):
    pipeline, events, sandbox = cobol_world

    def no_docker(*args, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(sandbox, "build", no_docker)
    with pytest.raises(PipelineError):
        pipeline.onboard("demo", "local://cobol-app")
    last = events.since(0, 50)[-1]
    assert last["kind"] == "onboard_failed" and "sandbox is unavailable" in last["detail"]
    assert [e["detail"] for e in events.since(0, 50) if e["kind"] == "onboard_stage"] == ["fetch", "detect", "build"]


def test_an_unexpected_error_still_ends_in_a_failure_event(cobol_world, monkeypatch):
    pipeline, events, _ = cobol_world
    monkeypatch.setattr(pipeline, "_build", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret internals")))
    with pytest.raises(PipelineError):
        pipeline.onboard("demo", "local://cobol-app")
    last = events.since(0, 50)[-1]
    assert last["kind"] == "onboard_failed" and "secret internals" not in last["detail"]


def test_the_admin_api_rejects_bad_input_and_busy_systems_immediately(cobol_world):
    from fastapi.testclient import TestClient
    from replic8.gateway import create_app

    pipeline, events, sandbox = cobol_world
    settings = pipeline.settings
    settings = Settings(data_dir=settings.data_dir, local_repo_root=settings.local_repo_root,
                        gateway_tokens=frozenset({"g" * 40}), admin_tokens=frozenset({"a" * 40}))
    app = create_app(settings, pipeline.registry, pipeline.executor, pipeline=pipeline, events=events)
    admin = {"Authorization": "Bearer " + "a" * 40}
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        bad = client.post("/v1/admin/systems", headers=admin, json={"system": "demo", "repo_url": "https://evil.example.com/a/b"})
        assert bad.status_code == 422
        pipeline._lock("demo").acquire()
        try:
            busy = client.post("/v1/admin/systems", headers=admin, json={"system": "demo", "repo_url": "local://cobol-app"})
        finally:
            pipeline._lock("demo").release()
        assert busy.status_code == 409


def test_the_admin_api_checks_known_values(cobol_world):
    from fastapi.testclient import TestClient
    from replic8.gateway import create_app

    pipeline, events, _ = cobol_world
    settings = Settings(data_dir=pipeline.settings.data_dir, local_repo_root=pipeline.settings.local_repo_root,
                        gateway_tokens=frozenset({"g" * 40}), admin_tokens=frozenset({"a" * 40}))
    app = create_app(settings, pipeline.registry, pipeline.executor, pipeline=pipeline, events=events)
    admin = {"Authorization": "Bearer " + "a" * 40}
    bad = [{"Bad Field": ["x"]}, {"request_id": []}, {"request_id": ["a=b"]}, {"request_id": ["x" * 65]},
           {"request_id": ["tab\there"]}, {"request_id": ["a"] * 6}, {"f" + "x" * 31: ["a"]}]
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        for known in bad:
            r = client.post("/v1/admin/systems", headers=admin,
                            json={"system": "demo", "repo_url": "local://cobol-app", "known_values": known})
            assert r.status_code == 422, known
        ok = client.post("/v1/admin/systems", headers=admin, json={
            "system": "demo", "repo_url": "local://cobol-app", "known_values": {"request_id": ["R-1001"]}})
        assert ok.status_code == 202
