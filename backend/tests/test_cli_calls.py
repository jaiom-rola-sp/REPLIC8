"""The command-line wrapper: finding programs, the guard on the form, and the real harness in the sandbox."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from replic8.extract import program_symbols
from replic8.guard import cli_problem
from replic8.config import SandboxLimits
from replic8.runtimes import LEGACY_IMAGE, argv_for, cli_argv, pin_local_image
from replic8.sandbox import Sandbox

LANGS = Path(__file__).parent / "fixtures" / "langs"
SCHEMA = {"type": "object", "properties": {"part_id": {"type": "string", "maxLength": 20}}, "required": ["part_id"]}
docker = pytest.mark.skipif(
    not shutil.which("docker")
    or subprocess.run(["docker", "image", "inspect", LEGACY_IMAGE], capture_output=True).returncode != 0,
    reason=f"needs Docker with {LEGACY_IMAGE} built")


def test_programs_are_found_by_their_entry_point():
    got = {(s.name, s.file) for d in ("c_orders", "pascal_payroll", "cli_perl", "cli_php", "cli_py")
           for s in program_symbols(LANGS / d)}
    assert got == {("main", "main.c"), ("payroll", "payroll.pas"), ("lookup", "lookup.pl"),
                   ("stock", "stock.php"), ("report", "report.py")}
    assert program_symbols(LANGS / "py_library") == []        # a library has no entry point


def test_the_command_is_built_by_replic8_from_a_checked_form():
    form = {"args": ["--part={part_id}"], "output": "keyvalue"}
    argv = argv_for("lookup", "bin/lookup.pl", form)
    assert argv[:2] == ["python3", "/replic8/call_cli.py"]
    assert json.loads(argv[2]) == {"exe": ["perl", "/app/bin/lookup.pl"], "args": ["--part={part_id}"], "output": "keyvalue"}
    assert json.loads(argv_for("main", "src/main.c", form)[2])["exe"] == ["/build/main"]
    assert argv_for("x", "src/../x.pl", form) == [] and argv_for("x", "a b.pl", form) == []
    assert cli_argv("src/app.java", form) == []                # java is not a program here


@pytest.mark.parametrize("args, why", [
    (["{part_id}"], ""),
    (["--part={part_id}"], ""),
    (["lookup", "{part_id}"], ""),
    (["{part_id}", "; rm -rf /"], "plain literal"),
    (["$(id)", "{part_id}"], "plain literal"),
    (["-x{part_id}"], "plain literal"),
    (["{nope}"], "not an input field"),
    (["{part_id}", "{part_id}"], "used twice"),
    (["literal"], "every input field"),
])
def test_guard_on_the_form(args, why):
    problem = cli_problem({"args": args, "output": "json"}, SCHEMA)
    assert (why in problem) if why else problem == "", problem


def test_guard_rejects_unbounded_strings_and_flag_then_optional_value():
    loose = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}
    assert "maxLength" in cli_problem({"args": ["{q}"], "output": "json"}, loose)
    opt = {"type": "object", "properties": {"q": {"type": "string", "maxLength": 9}}}
    assert "--flag=" in cli_problem({"args": ["--q", "{q}"], "output": "json"}, opt)
    assert cli_problem({"args": ["--q={q}"], "output": "json"}, opt) == ""


def run_in_sandbox(tmp_path, folder, exe_file, form, payload, build=False):
    data = tmp_path
    sandbox = Sandbox(data / "repos", frozenset({pin_local_image()}), SandboxLimits(timeout_s=30), builds_root=data / "builds")
    code = data / "repos" / "x"
    shutil.copytree(LANGS / folder, code)
    build_dir = None
    if build:
        build_dir = data / "builds" / "x"
        assert sandbox.build(pin_local_image(), code, build_dir, ["python3", "/replic8/build.py"]).ok
    argv = argv_for("p", exe_file, form)
    return sandbox.run(pin_local_image(), code, argv, json.dumps(payload).encode(), build_dir=build_dir)


@docker
def test_perl_keyvalue_and_optional_field(tmp_path):
    form = {"args": ["{part_id}", "{site}"], "output": "keyvalue"}
    got = run_in_sandbox(tmp_path, "cli_perl", "lookup.pl", form, {"part_id": "P-1", "site": "N"})
    assert json.loads(got.stdout) == {"part": "P-1", "on_hand": 12, "site": "N"}
    got = run_in_sandbox(tmp_path / "b", "cli_perl", "lookup.pl", form, {"part_id": "P-1"})
    assert json.loads(got.stdout)["site"] == "MAIN"         # the slot was dropped, not passed empty


@docker
def test_php_json_output(tmp_path):
    got = run_in_sandbox(tmp_path, "cli_php", "stock.php", {"args": ["{sku}"], "output": "json"}, {"sku": "A1"})
    assert json.loads(got.stdout) == {"sku": "A1", "price": 4.5}


@docker
def test_c_and_pascal_programs_are_built_then_called(tmp_path):
    got = run_in_sandbox(tmp_path, "c_orders", "main.c", {"args": ["{customer}"], "output": "keyvalue"},
                         {"customer": "C-9"}, build=True)
    assert json.loads(got.stdout) == {"customer": "C-9", "count": 3}
    got = run_in_sandbox(tmp_path / "p", "pascal_payroll", "payroll.pas", {"args": ["{hours}"], "output": "keyvalue"},
                         {"hours": 40}, build=True)
    assert json.loads(got.stdout) == {"gross": 800}


@docker
def test_values_cannot_become_flags_or_syntax(tmp_path):
    form = {"args": ["{part_id}"], "output": "keyvalue"}
    for bad in ({"part_id": "--help"}, {"part_id": "-1"}, {"part_id": "a\nb"}, {"part_id": "x" * 300}, {"part_id": ["a"]},
                {"part_id": True}, {}):
        got = run_in_sandbox(tmp_path / str(abs(hash(json.dumps(bad)))), "cli_perl", "lookup.pl", form, bad)
        assert got.exit_code == (4 if bad else 2) and not got.stdout, bad   # {} just runs the program with no argument; it dies
    shell = run_in_sandbox(tmp_path / "s", "cli_perl", "lookup.pl", form, {"part_id": "P; echo hacked $(id)"})
    assert json.loads(shell.stdout)["part"] == "P; echo hacked $(id)"      # plain data, never run


@docker
def test_missing_program_is_exit_3_and_failure_hides_details(tmp_path):
    got = run_in_sandbox(tmp_path, "cli_perl", "gone.pl", {"args": ["{p}"], "output": "keyvalue"}, {"p": "x"})
    assert got.exit_code == 3
    got = run_in_sandbox(tmp_path / "f", "cli_perl", "lookup.pl", {"args": ["{p}"], "output": "json"}, {"p": "P-1"})
    assert got.exit_code == 2 and not got.stdout
