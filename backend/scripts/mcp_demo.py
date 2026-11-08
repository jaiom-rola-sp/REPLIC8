"""REPLIC8 MCP demo: what an AI agent at Company A sees.

Connects to the gateway's MCP endpoint, lists the tools generated from the
legacy COBOL and Fortran systems, then answers "can we fix pump request
R-1001, and how fast?" by chaining three tools across both systems.

Usage (the gateway must be running, with both systems onboarded):
    REPLIC8_TOKEN=<gateway token> python scripts/mcp_demo.py [--url http://127.0.0.1:8000/mcp]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

PROTOCOL = "2025-06-18"


class Mcp:
    def __init__(self, url: str, token: str):
        self.url = url
        self.http = httpx.Client(timeout=60, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL,
        })
        self.next_id = 1

    def request(self, method: str, params: dict | None = None) -> dict:
        body = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}}
        self.next_id += 1
        resp = self.http.post(self.url, json=body)
        if resp.status_code != 200:
            sys.exit(f"{method} failed: HTTP {resp.status_code} {resp.text[:200]}")
        data = resp.json()
        if "error" in data:
            sys.exit(f"{method} failed: {data['error'].get('message')}")
        return data["result"]

    def call(self, tool: str, arguments: dict) -> dict:
        result = self.request("tools/call", {"name": tool, "arguments": arguments})
        if result.get("isError"):
            sys.exit(f"{tool} failed: {result['content'][0]['text']}")
        return result["structuredContent"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--request-id", default="R-1001")
    args = parser.parse_args()
    token = os.environ.get("REPLIC8_TOKEN")
    if not token:
        sys.exit("Set REPLIC8_TOKEN to a gateway token.")

    mcp = Mcp(args.url, token)
    info = mcp.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                      "clientInfo": {"name": "company-a-agent", "version": "1.0"}})
    print(f"Connected to {info['serverInfo']['name']} over MCP\n")

    print("Tools generated from legacy code:")
    for tool in mcp.request("tools/list")["tools"]:
        read_only = "read-only" if tool.get("annotations", {}).get("readOnlyHint") else "write"
        print(f"  {tool['name']:34} {read_only:9} {tool['description'][:70]}")

    def show(step: str, out: dict) -> dict:
        p = out["provenance"]
        print(f"\n{step}\n  {p['tool']}  <- {p['source']} @ {p['source_commit'][:10]} (v{p['version']}, {p['tier']})")
        print("  " + json.dumps(out["result"]))
        return out["result"]

    request = show("1. Company B (COBOL): look up the maintenance request",
                   mcp.call("maintenance.get_request", {"request_id": args.request_id}))
    if request.get("found") != "Y":
        sys.exit("Request not found.")
    stock = show("2. Company C (Fortran): check stock for that part",
                 mcp.call("inventory.check_stock", {"part_id": request["part_id"]}))
    ship = show("3. Company C (Fortran): shipping options to the well's region",
                mcp.call("inventory.get_shipping_options",
                         {"part_id": request["part_id"], "destination": request["site"]}))

    fastest = min(ship.get("items", []), key=lambda i: i["transit_days"], default=None)
    print("\nAnswer:")
    print(f"  Request {request['request_id']} needs {request['quantity']} x {request['part_id']} at well "
          f"{request['well_id']} ({request['site']}).")
    print(f"  {stock.get('on_hand', 0)} on hand in {stock.get('warehouse', '?')}.")
    if fastest:
        print(f"  Fastest: {fastest['carrier']}, {fastest['transit_days']} day(s), ${fastest['cost_usd']:.2f}.")


if __name__ == "__main__":
    main()
