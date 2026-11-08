"""Demo legacy systems (FR-10): extraction, shim protocol, and a real sandboxed run."""

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from replic8.config import SandboxLimits, Settings
from replic8.executor import Executor
from replic8.extract import extract_symbols
from replic8.gateway import create_app
from replic8.models import ContractTestResult, Operation
from replic8.registry import Registry
from replic8.runtimes import LEGACY_IMAGE, RUNTIMES, argv_for, callable_symbols, pin_local_image
from replic8.sandbox import Sandbox

from conftest import ALL_SCOPES, TOKEN

ROOT = Path(__file__).resolve().parents[2]
B = ROOT / "legacy" / "b-maintenance-cobol"
C = ROOT / "legacy" / "c-inventory-java"
COMMIT_B = "b" * 40
COMMIT_C = "c" * 40

spec = importlib.util.spec_from_file_location("shim", ROOT / "backend" / "runtime" / "shim.py")
shim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shim)


# ---------- extraction ----------

def test_extracts_cobol_paragraphs_without_entry_point():
    # The grammar doesn't know LINE SEQUENTIAL file clauses, so the file is "partly parsed",
    # but every paragraph it read is confirmed against the source.
    symbols, partial = extract_symbols(B)
    assert partial == ["src/MAINT.cbl"]
    names = {s.name: (s.file, s.line) for s in symbols}
    assert "MAIN-LOGIC" not in names
    assert {"GET-REQUEST", "LIST-OPEN-REQUESTS", "READ-INPUT"} <= set(names)
    file, line = names["GET-REQUEST"]
    assert file == "src/MAINT.cbl"
    assert (B / file).read_text().splitlines()[line - 1].strip() == "GET-REQUEST."


def test_extracts_java_methods_without_main():
    symbols, errors = extract_symbols(C)
    assert errors == []
    names = {s.name: (s.file, s.line) for s in symbols}
    assert {"checkStock", "getShippingOptions", "findPart"} <= set(names) and "main" not in names
    file, line = names["checkStock"]
    assert file == "src/com/subc/pil/Inventory.java"
    assert "void checkStock(" in (C / file).read_text().splitlines()[line - 1]


def test_extracts_fortran_subroutines(tmp_path):
    (tmp_path / "inv.f90").write_text("program p\ncontains\n  subroutine check_stock(x)\n    integer :: x\n  end subroutine check_stock\nend program p\n")
    symbols, errors = extract_symbols(tmp_path)
    assert errors == [] and [(s.name, s.line) for s in symbols] == [("check_stock", 3)]


def test_unparseable_file_is_reported_not_guessed(tmp_path):
    (tmp_path / "bad.f90").write_text("subroutine (((\n")
    symbols, partial = extract_symbols(tmp_path)
    assert symbols == [] and partial == ["bad.f90"]


def test_symbol_must_be_on_its_reported_line():
    from replic8.extract import _confirmed
    lines = ["       GET-REQUEST.", "  subroutine check_stock(part_id)", "    static void checkStock(String id) {"]
    assert _confirmed(lines, "GET-REQUEST", 1, "cobol")
    assert not _confirmed(lines, "DELETE-ALL", 1, "cobol")
    assert _confirmed(lines, "check_stock", 2, "fortran")
    assert not _confirmed(lines, "check_stock", 9, "fortran")
    assert _confirmed(lines, "checkStock", 3, "java")
    assert not _confirmed(lines, "deleteAll", 3, "java")


# ---------- runtime table ----------

def test_only_dispatchable_symbols_are_offered():
    assert sorted(s.name for s in callable_symbols(B, extract_symbols(B)[0])) == ["GET-REQUEST", "LIST-OPEN-REQUESTS"]
    assert sorted(s.name for s in callable_symbols(C, extract_symbols(C)[0])) == ["checkStock", "getShippingOptions"]


def test_argv_is_built_by_replic8():
    assert argv_for("GET-REQUEST", "src/MAINT.cbl") == ["python3", "/replic8/shim.py", "/build/maint", "GET-REQUEST"]
    assert argv_for("checkStock", "src/com/subc/pil/Inventory.java")[-2:] == ["/build/app.jar", "checkStock"]
    assert argv_for("check_stock", "src/inventory.f90")[-2:] == ["/build/inventory", "check_stock"]
    assert argv_for("x; rm -rf /", "src/MAINT.cbl") == []
    assert argv_for("main", "src/app.py") == []


# ---------- shim protocol (pure functions) ----------

def test_shim_converts_both_ways():
    assert shim.to_legacy({"part_id": "PMP-2210", "qty": 2}) == ["PART-ID=PMP-2210", "QTY=2"]
    out = shim.from_legacy("FOUND=Y\nWAREHOUSE=HOUSTON\nBEGIN-ITEMS\nCARRIER=GULF\nCOST-USD=840.00\n--\nCOUNT=1\n")
    assert out == {"found": "Y", "warehouse": "HOUSTON", "count": 1, "items": [{"carrier": "GULF", "cost_usd": 840.0}]}


@pytest.mark.parametrize("payload", [
    {"part_id": "A\nCHECK_STOCK"}, {"part_id": "A=B"}, {"PART": "x"}, {"part_id": ["x"]}, {"part_id": "x" * 65},
])
def test_shim_rejects_smuggled_input(payload):
    with pytest.raises(SystemExit):
        shim.to_legacy(payload)


def test_shim_turns_legacy_error_into_failure():
    with pytest.raises(SystemExit):
        shim.from_legacy("ERROR=DATA-FILE-UNAVAILABLE\n")


# ---------- real run: build in the sandbox, call through the gateway ----------

def _image_ready() -> bool:
    return bool(shutil.which("docker")) and subprocess.run(
        ["docker", "image", "inspect", LEGACY_IMAGE], capture_output=True).returncode == 0


@pytest.mark.skipif(not _image_ready(), reason=f"needs Docker with {LEGACY_IMAGE} built")
def test_end_to_end_cobol_and_java(tmp_path):
    data = tmp_path / "data"
    repos, builds = data / "repos", data / "builds"
    checkouts = {
        "maintenance": (B, repos / "acme__b-maint" / COMMIT_B, builds / "acme__b-maint" / COMMIT_B, COMMIT_B),
        "inventory": (C, repos / "acme__c-inv" / COMMIT_C, builds / "acme__c-inv" / COMMIT_C, COMMIT_C),
    }
    sandbox = Sandbox(repos, frozenset({pin_local_image()}), SandboxLimits(timeout_s=20), builds_root=builds)
    for src, code, build, _ in checkouts.values():
        shutil.copytree(src, code)
        result = sandbox.build(LEGACY_IMAGE, code, build, list(RUNTIMES["cobol"].build_argv))
        assert result.ok, result.stderr_tail

    def op(ns, name, symbol, file, line, props, required):
        return Operation(namespace=ns, name=name, description=name, tier="parsed", access="read",
                         source={"file": file, "line": line},
                         input_schema={"type": "object", "properties": props, "required": required,
                                       "additionalProperties": False},
                         output_schema={"type": "object", "required": ["found"]},
                         invocation={"image": LEGACY_IMAGE, "argv": argv_for(symbol, file)})

    sym_b = {s.name: s for s in extract_symbols(B)[0]}
    sym_c = {s.name: s for s in extract_symbols(C)[0]}
    reg = Registry(data)
    get_req = op("maintenance", "get_request", "GET-REQUEST", "src/MAINT.cbl", sym_b["GET-REQUEST"].line,
                 {"request_id": {"type": "string", "pattern": "^R-[0-9]{4}$"}}, ["request_id"])
    stock = op("inventory", "check_stock", "checkStock", "src/com/subc/pil/Inventory.java", sym_c["checkStock"].line,
               {"part_id": {"type": "string", "pattern": "^[A-Z]{3}-[0-9]{4}$"}}, ["part_id"])
    reg.publish("maintenance", "https://github.com/acme/b-maint.git", COMMIT_B, [get_req],
                {get_req.tool: ContractTestResult(passed=True, cases=1, source_commit=COMMIT_B)})
    reg.publish("inventory", "https://github.com/acme/c-inv.git", COMMIT_C, [stock],
                {stock.tool: ContractTestResult(passed=True, cases=1, source_commit=COMMIT_C)})

    app = create_app(Settings(data_dir=data, gateway_tokens=frozenset({TOKEN}), token_scopes=ALL_SCOPES), reg,
                     Executor(sandbox, repos))
    client = TestClient(app)
    auth = {"Authorization": f"Bearer {TOKEN}"}

    # Demo flow: A reads B's pump request, then checks C's stock for the same part.
    req = client.post("/v1/operations/maintenance.get_request", json={"input": {"request_id": "R-1001"}}, headers=auth)
    assert req.status_code == 200, req.text
    request = req.json()["result"]
    assert request["part_id"] == "PMP-2210" and request["site"] == "PERMIAN"
    assert req.json()["provenance"]["source"].startswith("src/MAINT.cbl:")

    inv = client.post("/v1/operations/inventory.check_stock", json={"input": {"part_id": request["part_id"]}}, headers=auth)
    assert inv.status_code == 200, inv.text
    assert inv.json()["result"]["on_hand"] == 12

    bad = client.post("/v1/operations/inventory.check_stock", json={"input": {"part_id": "PMP-2210\nX"}}, headers=auth)
    assert bad.status_code == 422
