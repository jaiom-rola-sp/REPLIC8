"""Admin API to grant and remove a token's scope at runtime (POST/DELETE /v1/admin/scopes)."""

import logging

import pytest
from fastapi.testclient import TestClient

from replic8.config import Settings, token_id
from replic8.gateway import create_app
from replic8.registry import Registry

from conftest import COMMIT, TOKEN, make_op, passed

ADMIN = "a" * 40
OTHER = "o" * 40  # starts with no scopes
WRITER = "w" * 40  # configured with maintenance.* (a REPLIC8_TOKEN_SCOPES scope)
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


class Exec:
    def call(self, op, version, payload):
        return {"id": payload["id"]}


@pytest.fixture
def client(data_dir):
    reg = Registry(data_dir)
    reg.publish("maintenance", "https://github.com/acme/legacy.git", COMMIT,
                [make_op("get_request"), make_op("close_request", access="write")],
                {"maintenance.get_request": passed(), "maintenance.close_request": passed()})
    reg.publish("inventory", "https://github.com/acme/stock.git", COMMIT,
                [make_op("check_stock", ns="inventory")], {"inventory.check_stock": passed()})
    settings = Settings(
        data_dir=data_dir,
        gateway_tokens=frozenset({TOKEN, OTHER, WRITER}),
        admin_tokens=frozenset({ADMIN}),
        token_scopes={token_id(TOKEN): frozenset({"maintenance.*"}),
                      token_id(WRITER): frozenset({"maintenance.*"})},
        write_allowlist=frozenset({"maintenance.close_request"}),
    )
    with TestClient(create_app(settings, reg, Exec()), base_url="http://127.0.0.1:8000") as c:
        yield c


def grant(c, target, scope, token=ADMIN):
    return c.post("/v1/admin/scopes", json={"token_id": token_id(target), "scope": scope}, headers=auth(token))


def remove(c, target, scope, token=ADMIN):
    return c.request("DELETE", "/v1/admin/scopes", json={"token_id": token_id(target), "scope": scope},
                     headers=auth(token))


def call(c, token, tool):
    return c.post(f"/v1/operations/{tool}", json={"input": {"id": "1"}}, headers=auth(token))


def rest_tools(c, token):
    return [o["tool"] for o in c.get("/v1/operations", headers=auth(token)).json()["operations"]]


def mcp(c, token, method, params=None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return c.post("/mcp", headers={**auth(token), **MCP_HEADERS}, json=body).json()["result"]


def mcp_tools(c, token):
    return [t["name"] for t in mcp(c, token, "tools/list")["tools"]]


def test_only_admin_tokens_can_change_scopes(client):
    body = {"token_id": token_id(OTHER), "scope": "inventory.*"}
    for headers in ({}, auth(TOKEN), auth(OTHER), auth("x" * 40)):
        assert client.post("/v1/admin/scopes", json=body, headers=headers).status_code == 401
        assert client.request("DELETE", "/v1/admin/scopes", json=body, headers=headers).status_code == 401
    assert call(client, OTHER, "inventory.check_stock").status_code == 403  # nothing changed


def test_admin_api_off_without_admin_tokens(data_dir):
    settings = Settings(data_dir=data_dir, gateway_tokens=frozenset({TOKEN}))
    c = TestClient(create_app(settings, Registry(data_dir), Exec()))
    r = c.post("/v1/admin/scopes", json={"token_id": token_id(TOKEN), "scope": "inventory.*"}, headers=auth(TOKEN))
    assert r.status_code == 403


@pytest.mark.parametrize("body,status", [
    ({"token_id": "not-hex-id!!", "scope": "inventory.*"}, 422),
    ({"token_id": "ABCDEF012345", "scope": "inventory.*"}, 422),      # must be lowercase
    ({"token_id": "0123456789a", "scope": "inventory.*"}, 422),       # 11 characters
    ({"token_id": OTHER, "scope": "inventory.*"}, 422),               # the raw token, not its id
    ({"token_id": "0" * 12, "scope": "inventory.*"}, 404),            # well formed, unknown
    ({"token_id": token_id(ADMIN), "scope": "inventory.*"}, 422),     # admin tokens are unscoped
    ({"token_id": token_id(OTHER), "scope": "*"}, 422),
    ({"token_id": token_id(OTHER), "scope": "inventory"}, 422),
    ({"token_id": token_id(OTHER), "scope": "Inventory.*"}, 422),
    ({"token_id": token_id(OTHER), "scope": "*.check_stock"}, 422),
    ({"token_id": token_id(OTHER), "scope": "inventory.*.x"}, 422),
    ({"token_id": token_id(OTHER)}, 422),                             # missing scope
    ({"token_id": token_id(OTHER), "scope": "inventory.*", "extra": 1}, 422),
])
def test_bad_input_is_rejected(client, body, status):
    assert client.post("/v1/admin/scopes", json=body, headers=auth(ADMIN)).status_code == status
    assert client.request("DELETE", "/v1/admin/scopes", json=body, headers=auth(ADMIN)).status_code == status
    assert call(client, OTHER, "inventory.check_stock").status_code == 403


def test_grant_takes_effect_immediately_for_rest_mcp_and_lists(client):
    assert call(client, OTHER, "inventory.check_stock").status_code == 403
    assert rest_tools(client, OTHER) == [] and mcp_tools(client, OTHER) == []

    r = grant(client, OTHER, "inventory.*")
    assert r.status_code == 200 and r.json() == {"token_id": token_id(OTHER), "scopes": ["inventory.*"],
                                                 "changed": True}
    assert call(client, OTHER, "inventory.check_stock").status_code == 200
    assert rest_tools(client, OTHER) == ["inventory.check_stock"]
    assert mcp_tools(client, OTHER) == ["inventory.check_stock"]
    res = mcp(client, OTHER, "tools/call", {"name": "inventory.check_stock", "arguments": {"id": "1"}})
    assert res["isError"] is False
    assert grant(client, OTHER, "inventory.*").json()["changed"] is False  # granting twice is harmless


def test_remove_takes_effect_immediately_for_granted_and_configured_scopes(client):
    grant(client, OTHER, "inventory.check_stock")
    assert call(client, OTHER, "inventory.check_stock").status_code == 200
    r = remove(client, OTHER, "inventory.check_stock")
    assert r.status_code == 200 and r.json()["scopes"] == [] and r.json()["changed"] is True
    assert call(client, OTHER, "inventory.check_stock").status_code == 403
    assert rest_tools(client, OTHER) == [] and mcp_tools(client, OTHER) == []
    res = mcp(client, OTHER, "tools/call", {"name": "inventory.check_stock", "arguments": {"id": "1"}})
    assert res["isError"] is True

    # A scope from REPLIC8_TOKEN_SCOPES can be removed too (e.g. a leaked token), and granted back.
    assert call(client, TOKEN, "maintenance.get_request").status_code == 200
    assert remove(client, TOKEN, "maintenance.*").json()["scopes"] == []
    assert call(client, TOKEN, "maintenance.get_request").status_code == 403
    assert mcp_tools(client, TOKEN) == []
    assert grant(client, TOKEN, "maintenance.*").json()["scopes"] == ["maintenance.*"]
    assert call(client, TOKEN, "maintenance.get_request").status_code == 200
    assert remove(client, OTHER, "maintenance.*").json()["changed"] is False  # nothing to remove


def test_write_operations_are_never_granted(client):
    # Granting a write tool by name is refused, even though it is in REPLIC8_WRITE_OPS.
    r = grant(client, OTHER, "maintenance.close_request")
    assert r.status_code == 422 and "write" in r.json()["detail"]
    # A namespace grant opens the reads but not the write in it.
    grant(client, OTHER, "maintenance.*")
    assert call(client, OTHER, "maintenance.get_request").status_code == 200
    assert call(client, OTHER, "maintenance.close_request").status_code == 403
    assert "maintenance.close_request" not in rest_tools(client, OTHER)
    assert "maintenance.close_request" not in mcp_tools(client, OTHER)
    res = mcp(client, OTHER, "tools/call", {"name": "maintenance.close_request", "arguments": {"id": "1"}})
    assert res["isError"] is True
    # The configured path is unchanged: a REPLIC8_TOKEN_SCOPES scope plus REPLIC8_WRITE_OPS still works.
    assert call(client, WRITER, "maintenance.close_request").status_code == 200


def test_every_change_is_audited_with_the_admins_token_id(client, caplog):
    with caplog.at_level(logging.INFO, logger="replic8.audit"):
        grant(client, OTHER, "inventory.*")
        remove(client, OTHER, "inventory.*")
        grant(client, OTHER, "maintenance.close_request")  # refused
    admin, target = token_id(ADMIN), token_id(OTHER)
    text = caplog.text
    assert f"scope_grant admin={admin} token={target} scope=inventory.* changed=True" in text
    assert f"scope_remove admin={admin} token={target} scope=inventory.* changed=True" in text
    assert f"scope_grant_refused admin={admin} token={target} scope=maintenance.close_request reason=write" in text
    assert ADMIN not in text and OTHER not in text  # ids only, never the tokens


def test_restart_goes_back_to_the_configured_scopes(data_dir, client):
    grant(client, OTHER, "inventory.*")
    assert call(client, OTHER, "inventory.check_stock").status_code == 200
    settings = Settings(data_dir=data_dir, gateway_tokens=frozenset({TOKEN, OTHER}), admin_tokens=frozenset({ADMIN}),
                        token_scopes={token_id(TOKEN): frozenset({"maintenance.*"})})
    fresh = TestClient(create_app(settings, Registry(data_dir), Exec()))
    assert call(fresh, OTHER, "inventory.check_stock").status_code == 403
