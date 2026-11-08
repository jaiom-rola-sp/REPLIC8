"""The sandbox image builds C and Pascal programs and syntax-checks Python, Perl and PHP (FR-14).

Each case copies a tiny fixture into a cloned-repo layout, builds it with the same step the pipeline uses,
and runs what came out inside the sandbox.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from replic8.config import SandboxLimits
from replic8.runtimes import LEGACY_IMAGE, RUNTIMES, pin_local_image
from replic8.sandbox import Sandbox

pytestmark = pytest.mark.skipif(
    not shutil.which("docker")
    or subprocess.run(["docker", "image", "inspect", LEGACY_IMAGE], capture_output=True).returncode != 0,
    reason=f"needs Docker with {LEGACY_IMAGE} built",
)

FIXTURES = Path(__file__).parent / "fixtures" / "langs"
COMMIT = "a" * 40


def build(tmp_path, fixture, language):
    data = tmp_path / "data"
    repos, builds = data / "repos", data / "builds"
    code, out = repos / "acme__t" / COMMIT, builds / "acme__t" / COMMIT
    shutil.copytree(FIXTURES / fixture, code)
    sandbox = Sandbox(repos, frozenset({pin_local_image()}), SandboxLimits(timeout_s=60), builds_root=builds)
    result = sandbox.build(LEGACY_IMAGE, code, out, list(RUNTIMES[language].build_argv))
    return sandbox, code, out, result


def run(sandbox, code, out, *argv):
    result = sandbox.run(LEGACY_IMAGE, code, list(argv), b"", build_dir=out)
    return result.exit_code, result.stdout.decode()


def test_every_new_language_has_a_runtime_in_the_shared_image():
    for language in ("c", "pascal", "python", "perl", "php"):
        assert RUNTIMES[language].image == LEGACY_IMAGE and RUNTIMES[language].build_argv


def test_c_with_a_header_and_two_source_files_builds_and_runs(tmp_path):
    sandbox, code, out, result = build(tmp_path, "c_orders", "c")
    assert result.ok, result.stderr_tail
    assert run(sandbox, code, out, "/build/main", "C-100") == (0, "customer=C-100\ncount=3\n")
    assert run(sandbox, code, out, "/build/main", "X-1")[1].endswith("count=0\n")


def test_a_pascal_program_builds_and_runs(tmp_path):
    sandbox, code, out, result = build(tmp_path, "pascal_payroll", "pascal")
    assert result.ok, result.stderr_tail
    assert run(sandbox, code, out, "/build/payroll", "40") == (0, "gross=800\n")


@pytest.mark.parametrize("fixture,language", [("py_billing", "python"), ("perl_report", "perl"), ("php_catalog", "php")])
def test_a_valid_script_passes_its_syntax_check(tmp_path, fixture, language):
    _, _, _, result = build(tmp_path, fixture, language)
    assert result.ok, result.stderr_tail


@pytest.mark.parametrize("fixture,language", [("py_python2", "python"), ("perl_broken", "perl"), ("php_broken", "php")])
def test_a_broken_script_fails_the_build_instead_of_the_first_call(tmp_path, fixture, language):
    _, _, _, result = build(tmp_path, fixture, language)
    assert not result.ok


def test_a_repo_with_no_program_fails_clearly(tmp_path):
    (tmp_path / "empty").mkdir()
    shutil.copy(FIXTURES / "c_orders" / "orders.c", tmp_path / "empty" / "orders.c")
    data = tmp_path / "data"
    repos, builds = data / "repos", data / "builds"
    code, out = repos / "acme__t" / COMMIT, builds / "acme__t" / COMMIT
    shutil.copytree(tmp_path / "empty", code)
    sandbox = Sandbox(repos, frozenset({pin_local_image()}), SandboxLimits(timeout_s=60), builds_root=builds)
    result = sandbox.build(LEGACY_IMAGE, code, out, list(RUNTIMES["c"].build_argv))
    assert not result.ok and "main()" in result.stderr_tail


def test_the_protocol_command_is_never_built_for_languages_that_do_not_speak_it():
    from replic8.runtimes import argv_for
    for file in ("src/orders.c", "src/pay.pas", "src/report.pl", "src/catalog.php"):
        assert argv_for("get_part", file) == [], file
    assert argv_for("GET-REQUEST", "src/MAINT.cbl")[-1] == "GET-REQUEST"      # the three that do speak it still work
