import logging

import pytest
from fastapi.testclient import TestClient

from replic8.config import Settings
from replic8.executor import CallError, validate_input
from replic8.gateway import create_app
from replic8.registry import Registry

from conftest import COMMIT, TOKEN, make_op, passed

AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeExecutor:
    def __init__(self, result=None, error=None):
        self.result = result or {"id": "R-1"}
        self.error = error
        self.calls = []

    def call(self, op, version, payload):
        validate_input(op, payload)
        self.calls.append((op.tool, payload))
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def setup(data_dir):
    reg = Registry(data_dir)
    reg.publish(
        "maintenance", "https://github.com/acme/legacy.git", COMMIT,
        [make_op("get_request"), make_op("delete_request", access="write")],
        {"maintenance.get_request": passed(), "maintenance.delete_request": passed()},
    )
    settings = Settings(data_dir=data_dir, gateway_tokens=frozenset({TOKEN}), rate_limit_per_minute=5)
    executor = FakeExecutor()
    return TestClient(create_app(settings, reg, executor)), executor


def test_refuses_to_start_without_tokens(data_dir):
    with pytest.raises(RuntimeError):
        create_app(Settings(data_dir=data_dir), Registry(data_dir), FakeExecutor())


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": f"Basic {TOKEN}"}])
def test_requires_valid_token(setup, headers):
    client, _ = setup
    assert client.get("/v1/operations", headers=headers).status_code == 401
    assert client.post("/v1/operations/maintenance.get_request", json={"input": {"id": "1"}},
                       headers=headers).status_code == 401


def test_health_is_open_and_docs_are_off(setup):
    client, _ = setup
    assert client.get("/health").json() == {"status": "ok"}
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_lists_operations_with_trust_labels(setup):
    client, _ = setup
    ops = {o["tool"]: o for o in client.get("/v1/operations", headers=AUTH).json()["operations"]}
    assert ops["maintenance.get_request"]["enabled"] is True
    assert ops["maintenance.delete_request"]["enabled"] is False
    assert ops["maintenance.get_request"]["source"] == "src/maint.py:3"
    assert ops["maintenance.get_request"]["tier"] == "parsed"


def test_read_call_returns_result_with_provenance(setup):
    client, executor = setup
    resp = client.post("/v1/operations/maintenance.get_request", json={"input": {"id": "R-1"}}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["provenance"]["source_commit"] == COMMIT
    assert executor.calls == [("maintenance.get_request", {"id": "R-1"})]


def test_write_operations_are_blocked(setup):
    client, executor = setup
    resp = client.post("/v1/operations/maintenance.delete_request", json={"input": {"id": "R-1"}}, headers=AUTH)
    assert resp.status_code == 403
    assert executor.calls == []


def test_input_is_checked_against_schema(setup):
    client, executor = setup
    for bad in ({"id": 5}, {"id": "x" * 50}, {"id": "1", "extra": "y"}, {}):
        resp = client.post("/v1/operations/maintenance.get_request", json={"input": bad}, headers=AUTH)
        assert resp.status_code == 422
    assert executor.calls == []


def test_unknown_and_malformed_tool_names(setup):
    client, _ = setup
    for tool in ("maintenance.nope", "nope", "../x", "MAINT.get"):
        resp = client.post(f"/v1/operations/{tool}", json={"input": {}}, headers=AUTH)
        assert resp.status_code == 404


def test_large_body_rejected(setup):
    client, executor = setup
    resp = client.post("/v1/operations/maintenance.get_request", headers=AUTH,
                       json={"input": {"id": "x" * 100_000}})
    assert resp.status_code == 413
    assert executor.calls == []


def test_legacy_errors_are_not_leaked(data_dir):
    reg = Registry(data_dir)
    reg.publish("maintenance", "https://github.com/acme/legacy.git", COMMIT, [make_op()],
                {"maintenance.get_request": passed()})
    settings = Settings(data_dir=data_dir, gateway_tokens=frozenset({TOKEN}))
    client = TestClient(create_app(settings, reg, FakeExecutor(error=RuntimeError("DB password=hunter2"))),
                        raise_server_exceptions=False)
    resp = client.post("/v1/operations/maintenance.get_request", json={"input": {"id": "1"}}, headers=AUTH)
    assert resp.status_code == 500 and "hunter2" not in resp.text

    client = TestClient(create_app(settings, reg, FakeExecutor(error=CallError("legacy system timed out", 504))))
    resp = client.post("/v1/operations/maintenance.get_request", json={"input": {"id": "1"}}, headers=AUTH)
    assert resp.status_code == 504


def test_rate_limit(setup):
    client, _ = setup
    codes = [client.get("/v1/operations", headers=AUTH).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[-1] == 429


def test_audit_log_has_no_caller_input(setup, caplog):
    client, _ = setup
    with caplog.at_level(logging.INFO, logger="replic8.audit"):
        client.post("/v1/operations/maintenance.get_request", json={"input": {"id": "SECRET-42"}}, headers=AUTH)
    assert "maintenance.get_request" in caplog.text and "SECRET-42" not in caplog.text and TOKEN not in caplog.text
