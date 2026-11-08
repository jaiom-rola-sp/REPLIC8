"""Calling Python functions by name (FR-14, B3): the command, the parameter lists, the guard, and the harness itself.

The first group needs no Docker. The second runs runtime/call_python.py in the real sandbox, once for every
promise it makes: answers become JSON objects, nothing the legacy code prints or reads gets through, and errors
are reported by type only.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from replic8.config import SandboxLimits
from replic8.extract import extract_symbols
from replic8.guard import Symbol, validate_proposal
from replic8.models import Tier
from replic8.prompts import build_context, propose_messages
from replic8.runtimes import LEGACY_IMAGE, argv_for, callable_symbols, pin_local_image
from replic8.sandbox import Sandbox

LIB = Path(__file__).parent / "fixtures" / "langs" / "py_library"
needs_image = pytest.mark.skipif(
    not shutil.which("docker")
    or subprocess.run(["docker", "image", "inspect", LEGACY_IMAGE], capture_output=True).returncode != 0,
    reason=f"needs Docker with {LEGACY_IMAGE} built",
)


# ---------- no Docker needed ----------

def test_the_python_command_is_built_by_replic8_and_refuses_anything_odd():
    assert argv_for("invoice_total", "billing/lib.py") == ["python3", "/replic8/call_python.py", "/app/billing/lib.py", "invoice_total"]
    for symbol, file in [("x; rm -rf /", "lib.py"), ("a-b", "lib.py"), ("1abc", "lib.py"), ("f", "../lib.py"), ("f", "a/../lib.py"),
                         ("f", "lib.py; ls"), ("f", "/etc/passwd"), ("f", "lib py.py"), ("", "lib.py")]:
        assert argv_for(symbol, file) == [], (symbol, file)


def test_parameters_travel_with_each_function_and_exclude_what_json_cannot_fill():
    symbols = {s.name: s for s in extract_symbols(LIB)[0]}
    assert symbols["invoice_total"].params == (("quantity", True), ("unit_price", True), ("tax_rate", False))
    assert symbols["typed"].params == (("a", True), ("b", False))            # annotations handled; *rest and **extra skipped
    assert symbols["keyword_only"].params == (("a", True), ("mode", False))  # keyword-only parameters work by name
    assert symbols["reads_stdin"].params == ()
    assert "_private" not in symbols


def test_every_public_python_function_is_a_candidate_but_c_is_not_callable_yet(tmp_path):
    (tmp_path / "a.py").write_text("def get_part(x):\n    return x\n")
    (tmp_path / "b.c").write_text("int order_count(int x) { return x; }\nint main(void) { return 0; }\n")
    symbols, _ = extract_symbols(tmp_path)
    assert {s.name for s in symbols} == {"get_part", "order_count"}
    assert {s.name for s in callable_symbols(tmp_path, symbols)} == {"get_part"}


def proposal(**over):
    item = {"name": "invoice_total", "symbol": "invoice_total", "file": "lib.py", "line": 12, "access": "read",
            "description": "Total with tax", "output_schema": {"type": "object"},
            "input_schema": {"type": "object", "additionalProperties": False,
                             "properties": {"quantity": {"type": "number"}, "unit_price": {"type": "number"}, "tax_rate": {"type": "number"}},
                             "required": ["quantity", "unit_price"]}}
    item.update(over)
    return json.dumps({"operations": [item]})


def check(raw):
    symbols, _ = extract_symbols(LIB)
    line = next(s.line for s in symbols if s.name == "invoice_total")
    raw = raw.replace('"line": 12', f'"line": {line}')
    return validate_proposal(raw, namespace="billing", tier=Tier.parsed, repo_root=LIB, image=LEGACY_IMAGE, argv_for=argv_for, symbols=symbols)


def test_a_proposal_that_matches_the_real_parameters_is_accepted_with_replic8_building_the_command():
    accepted, rejected = check(proposal())
    assert [op.tool for op in accepted] == ["billing.invoice_total"] and rejected == {}
    assert accepted[0].invocation.argv == ["python3", "/replic8/call_python.py", "/app/lib.py", "invoice_total"]


@pytest.mark.parametrize("schema,reason", [
    ({"properties": {"quantity": {}, "unit_price": {}, "qty": {}}, "required": ["quantity", "unit_price"]}, "parameter names"),
    ({"properties": {"quantity": {}}, "required": ["quantity"]}, "missing required"),
    ({"properties": {"quantity": {}, "unit_price": {}}, "required": ["quantity"]}, "required must list"),
])
def test_a_proposal_whose_inputs_cannot_call_the_function_is_rejected_with_a_reason(schema, reason):
    accepted, rejected = check(proposal(input_schema={"type": "object", "additionalProperties": False, **schema}))
    assert accepted == [] and reason in rejected["billing.invoice_total"]


def test_the_model_is_shown_real_signatures_and_the_python_rules():
    symbols, _ = extract_symbols(LIB)
    ctx = build_context(LIB, symbols)
    system, user = propose_messages("billing", Tier.parsed, ctx, symbols)
    assert "invoice_total(quantity, unit_price, tax_rate=<default>)" in user
    assert "keyword_only(a, mode=<default>)" in user
    assert "How replic8 calls a Python function" in system and "keyword arguments" in system
    assert "How replic8 calls a COBOL, Fortran or Java function" in system            # the protocol rules are labelled, not dropped


# ---------- the harness, in the real sandbox ----------

@pytest.fixture(scope="module")
def box(tmp_path_factory):
    data = tmp_path_factory.mktemp("py") / "data"
    repos = data / "repos"
    code = repos / "acme__lib" / ("a" * 40)
    shutil.copytree(LIB, code)
    return Sandbox(repos, frozenset({pin_local_image()}), SandboxLimits(timeout_s=30), builds_root=data / "builds"), code


def call(box, function, payload, file="lib.py"):
    sandbox, code = box
    argv = argv_for(function, file) or ["python3", "/replic8/call_python.py", f"/app/{file}", function]
    result = sandbox.run(LEGACY_IMAGE, code, argv, json.dumps(payload).encode())
    return result.exit_code, result.stdout.decode(), result.stderr_tail if isinstance(result.stderr_tail, str) else result.stderr_tail.decode()


@needs_image
def test_the_fixture_passes_the_build_step_syntax_check(tmp_path):
    data = tmp_path / "data"
    repos, builds = data / "repos", data / "builds"
    code, out = repos / "acme__lib" / ("a" * 40), builds / "acme__lib" / ("a" * 40)
    shutil.copytree(LIB, code)
    sandbox = Sandbox(repos, frozenset({pin_local_image()}), SandboxLimits(timeout_s=60), builds_root=builds)
    from replic8.runtimes import RUNTIMES
    assert sandbox.build(LEGACY_IMAGE, code, out, list(RUNTIMES["python"].build_argv)).ok


@needs_image
def test_a_function_is_called_with_keyword_arguments_and_defaults_apply(box):
    assert json.loads(call(box, "invoice_total", {"quantity": 2, "unit_price": 10})[1]) == {"total": 22.0}
    assert json.loads(call(box, "invoice_total", {"quantity": 2, "unit_price": 10, "tax_rate": 0})[1]) == {"total": 20}
    assert json.loads(call(box, "keyword_only", {"a": 1, "mode": "slow"})[1]) == {"a": 1, "mode": "slow"}


@needs_image
def test_answers_always_come_back_as_a_json_object(box):
    assert json.loads(call(box, "list_items", {"customer": "C-1"})[1]) == {"items": [{"sku": "A1", "qty": 2}, {"sku": "B7", "qty": 1}]}
    assert json.loads(call(box, "customer_name", {"customer_id": "C-1"})[1]) == {"result": "ACME Corp"}
    fancy = json.loads(call(box, "fancy", {"x": 1})[1])
    assert fancy == {"when": "2026-11-07", "amount": "12.50", "tags": ["a", "b"]}     # dates, decimals and sets become JSON


@needs_image
def test_nothing_the_legacy_code_prints_or_writes_reaches_the_caller(box):
    for function, payload in [("noisy", {"x": 1}), ("customer_name", {"customer_id": "C-1"})]:
        code, out, _ = call(box, function, payload)
        assert code == 0
        json.loads(out)                                                     # the whole of stdout is one JSON document
        assert "module loaded" not in out and "debug output" not in out and "raw write" not in out


@needs_image
def test_bad_input_is_exit_1_and_a_missing_function_is_exit_3(box):
    assert call(box, "invoice_total", {"quantity": 2})[0] == 1                       # a required argument is missing
    assert call(box, "invoice_total", {"quantity": 2, "unit_price": 1, "color": "red"})[0] == 1   # an unknown argument
    assert call(box, "no_such_function", {})[0] == 3
    assert call(box, "keyword_only", {"a": 1, "mode": "x"}, file="missing.py")[0] == 3
    assert call(box, "f", {}, file="../etc/passwd")[0] == 1                          # a path outside /app is refused
    assert call(box, "invoice_total", [1, 2])[0] == 1                                # input must be an object


@needs_image
def test_a_failing_function_is_exit_2_and_its_message_is_never_passed_on(box):
    code, out, err = call(box, "broken", {"x": 1})
    assert code == 2 and out == "" and "ValueError" in err and "secret detail" not in err
    assert call(box, "exits", {"x": 1})[0] == 2                                      # sys.exit() inside legacy code
    assert call(box, "reads_stdin", {})[0] == 2                                      # stdin is empty: EOFError, not a hang
    assert call(box, "not_json", {"x": 1})[0] == 2                                   # NaN is not JSON
    code, _, err = call(box, "anything", {}, file="bad_import.py")
    assert code == 2 and "import failed" in err and "fails when imported" not in err
