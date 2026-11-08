import logging

import pytest
from fastapi.testclient import TestClient

from replic8.config import ConfigError, Settings, token_id
from replic8.gateway import create_app
from replic8.registry import Registry
from replic8.validator import Denied, Validator

from conftest import COMMIT, TOKEN, make_op, passed
from test_gateway import FakeExecutor

OTHER = "o" * 40  # second token
NO_SCOPE = "n" * 40  # configured token with no scope entry


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def registry(data_dir):
    reg = Registry(data_dir)
    reg.publish("maintenance", "https://github.com/acme/legacy.git", COMMIT,
                [make_op("get_request"), make_op("delete_request", access="write")],
                {"maintenance.get_request": passed(), "maintenance.delete_request": passed()})
    reg.publish("inventory", "https://github.com/acme/stock.git", COMMIT,
                [make_op("get_part", ns="inventory"), make_op("get_bin", ns="inventory")],
                {"inventory.get_part": passed(), "inventory.get_bin": passed()})
    return reg


@pytest.fixture
def settings(data_dir):
    return Settings(
        data_dir=data_dir,
        gateway_tokens=frozenset({TOKEN, OTHER, NO_SCOPE}),
        token_scopes={
            token_id(TOKEN): frozenset({"maintenance.*"}),
            token_id(OTHER): frozenset({"inventory.get_part"}),
        },
    )


@pytest.fixture
def client(settings, registry):
    executor = FakeExecutor()
    return TestClient(create_app(settings, registry, executor)), executor


def test_namespace_scope_allows_only_that_namespace(client):
    c, executor = client
    ok = c.post("/v1/operations/maintenance.get_request", json={"input": {"id": "1"}}, headers=auth(TOKEN))
    assert ok.status_code == 200
    blocked = c.post("/v1/operations/inventory.get_part", json={"input": {"id": "1"}}, headers=auth(TOKEN))
    assert blocked.status_code == 403
    assert executor.calls == [("maintenance.get_request", {"id": "1"})]


def test_single_tool_scope(client):
    c, _ = client
    assert c.post("/v1/operations/inventory.get_part", json={"input": {"id": "1"}},
                  headers=auth(OTHER)).status_code == 200
    for tool in ("inventory.get_bin", "maintenance.get_request"):
        assert c.post(f"/v1/operations/{tool}", json={"input": {"id": "1"}},
                      headers=auth(OTHER)).status_code == 403


def test_token_without_scopes_gets_nothing(client):
    c, executor = client
    resp = c.post("/v1/operations/maintenance.get_request", json={"input": {"id": "1"}}, headers=auth(NO_SCOPE))
    assert resp.status_code == 403
    assert c.get("/v1/operations", headers=auth(NO_SCOPE)).json() == {"operations": []}
    assert executor.calls == []


def test_out_of_scope_unknown_tool_is_403_not_404(client):
    """A token can't probe other namespaces to learn which tools exist."""
    c, _ = client
    resp = c.post("/v1/operations/inventory.does_not_exist", json={"input": {}}, headers=auth(TOKEN))
    assert resp.status_code == 403


def test_listing_shows_only_tools_in_scope(client):
    c, _ = client
    tools = [o["tool"] for o in c.get("/v1/operations", headers=auth(TOKEN)).json()["operations"]]
    assert tools == ["maintenance.delete_request", "maintenance.get_request"]
    tools = [o["tool"] for o in c.get("/v1/operations", headers=auth(OTHER)).json()["operations"]]
    assert tools == ["inventory.get_part"]


def test_scope_block_is_audited_without_the_token(client, caplog):
    c, _ = client
    with caplog.at_level(logging.INFO, logger="replic8.audit"):
        c.post("/v1/operations/inventory.get_part", json={"input": {"id": "SECRET-1"}}, headers=auth(TOKEN))
    assert "outcome=scope_blocked" in caplog.text and token_id(TOKEN) in caplog.text
    assert TOKEN not in caplog.text and "SECRET-1" not in caplog.text


def test_validate_call_works_without_the_web_layer(settings, registry):
    """What a future MCP server would call directly."""
    v = Validator(settings, registry)
    approved = v.validate_call(TOKEN, "maintenance.get_request", {"id": "R-1"})
    assert approved.who == token_id(TOKEN) and approved.op.tool == "maintenance.get_request"
    assert v.validate_call(TOKEN, None, None).op is None

    cases = [
        ("wrong-token", "maintenance.get_request", {"id": "1"}, 401),
        (TOKEN, "../x", {"id": "1"}, 404),
        (TOKEN, "inventory.get_part", {"id": "1"}, 403),
        (TOKEN, "maintenance.nope", {"id": "1"}, 404),
        (TOKEN, "maintenance.delete_request", {"id": "1"}, 403),
        (TOKEN, "maintenance.get_request", {"id": "x" * 70_000}, 413),
        (TOKEN, "maintenance.get_request", {"id": 5}, 422),
    ]
    for token, tool, args, status in cases:
        with pytest.raises(Denied) as exc:
            v.validate_call(token, tool, args)
        assert exc.value.status == status, (tool, args)


def test_write_allowlist_still_needs_scope(data_dir, registry):
    settings = Settings(data_dir=data_dir, gateway_tokens=frozenset({OTHER}),
                        token_scopes={token_id(OTHER): frozenset({"inventory.*"})},
                        write_allowlist=frozenset({"maintenance.delete_request"}))
    with pytest.raises(Denied) as exc:
        Validator(settings, registry).validate_call(OTHER, "maintenance.delete_request", {"id": "1"})
    assert exc.value.status == 403


def test_config_rejects_bad_scopes(data_dir):
    with pytest.raises(ConfigError, match="unknown token id"):
        Settings(data_dir=data_dir, gateway_tokens=frozenset({TOKEN}),
                 token_scopes={"0" * 12: frozenset({"maintenance.*"})}).validate()
    for bad in ("*", "maintenance", "maintenance.*.x", "Maintenance.*", "*.get_request"):
        with pytest.raises(ConfigError, match="invalid scope"):
            Settings(data_dir=data_dir, gateway_tokens=frozenset({TOKEN}),
                     token_scopes={token_id(TOKEN): frozenset({bad})}).validate()


def test_scopes_are_read_from_env(data_dir, monkeypatch):
    monkeypatch.setenv("REPLIC8_DATA_DIR", str(data_dir))
    monkeypatch.setenv("REPLIC8_GATEWAY_TOKENS", f"{TOKEN},{OTHER}")
    monkeypatch.setenv("REPLIC8_TOKEN_SCOPES",
                       f"{token_id(TOKEN)}=maintenance.*|inventory.*, {token_id(OTHER)}=inventory.get_part")
    s = Settings.from_env()
    assert s.token_scopes == {token_id(TOKEN): frozenset({"maintenance.*", "inventory.*"}),
                              token_id(OTHER): frozenset({"inventory.get_part"})}
