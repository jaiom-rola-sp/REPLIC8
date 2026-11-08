import shutil
import subprocess

import pytest

from replic8.config import SandboxLimits
from replic8.executor import CallError, Executor
from replic8.sandbox import OutputSchemaError
from replic8.models import WrapperVersion
from replic8.sandbox import Sandbox, SandboxError, build_command

from conftest import COMMIT, make_op, passed

IMAGE = "alpine:3.20"


def test_command_has_every_hardening_flag(tmp_path):
    cmd = build_command("n", IMAGE, tmp_path, ["echo", "hi"], SandboxLimits())
    joined = " ".join(cmd)
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "--security-opt no-new-privileges",
                 "--pids-limit", "--memory 256m", "--user 65534:65534", "readonly", "--log-driver none"):
        assert flag in joined
    assert cmd[-3:] == [IMAGE, "echo", "hi"]


def test_rejects_unlisted_image_and_outside_dirs(tmp_path):
    repos = tmp_path / "repos"
    (repos / "x").mkdir(parents=True)
    box = Sandbox(repos, frozenset({IMAGE}), SandboxLimits())
    with pytest.raises(SandboxError):
        box.run("evil/image", repos / "x", ["true"], b"{}")
    with pytest.raises(SandboxError):
        box.run(IMAGE, tmp_path, ["true"], b"{}")
    with pytest.raises(SandboxError):
        box.run(IMAGE, repos / "x" / ".." / "..", ["true"], b"{}")
    with pytest.raises(SandboxError):
        box.run(IMAGE, repos / "x", ["true"], b"x" * 100_000)


def _docker_ready() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0


docker = pytest.mark.skipif(not _docker_ready(), reason=f"needs Docker with {IMAGE} pulled")


@pytest.fixture
def box(tmp_path):
    code = tmp_path / "repos" / "acme__legacy" / COMMIT
    code.mkdir(parents=True)
    (code / "data.txt").write_text("legacy\n")
    limits = SandboxLimits(timeout_s=5, max_output_bytes=10_000)
    return Sandbox(tmp_path / "repos", frozenset({IMAGE}), limits), code


def sh(script):
    return ["sh", "-c", script]


@docker
def test_input_arrives_on_stdin_only(box):
    sandbox, code = box
    result = sandbox.run(IMAGE, code, ["cat"], b'{"id":"$(reboot)"}')
    assert result.ok and result.stdout == b'{"id":"$(reboot)"}'


@docker
def test_no_network(box):
    sandbox, code = box
    result = sandbox.run(IMAGE, code, sh("wget -T 2 -q -O- http://1.1.1.1 && echo reached"), b"")
    assert b"reached" not in result.stdout and result.exit_code != 0


@docker
def test_filesystem_is_read_only_and_user_is_unprivileged(box):
    sandbox, code = box
    script = "id -u; touch /app/x 2>/dev/null && echo app-writable; touch /etc/x 2>/dev/null && echo root-writable; cat data.txt"
    result = sandbox.run(IMAGE, code, sh(script), b"")
    assert result.stdout.decode().split() == ["65534", "legacy"]
    assert not (code / "x").exists()


@docker
def test_timeout_kills_the_container(box):
    sandbox, code = box
    result = sandbox.run(IMAGE, code, ["sleep", "60"], b"")
    assert result.timed_out and not result.ok


@docker
def test_output_is_capped(box):
    sandbox, code = box
    result = sandbox.run(IMAGE, code, sh("yes legacy"), b"")
    assert result.output_too_large and len(result.stdout) <= 10_000


@docker
def test_executor_end_to_end(box):
    sandbox, code = box
    op = make_op()
    op = op.model_copy(update={"invocation": op.invocation.model_copy(update={"image": IMAGE, "argv": ["cat"]})})
    version = WrapperVersion(system="maintenance", version=1, source_commit=COMMIT,
                             repo_url="https://github.com/acme/legacy.git", operations=[op],
                             tests={op.tool: passed()})
    executor = Executor(sandbox, code.parent.parent)
    assert executor.call(op, version, {"id": "R-7"}) == {"id": "R-7"}
    with pytest.raises(CallError):
        executor.call(op, version, {"id": 7})

    bad = op.model_copy(update={"invocation": op.invocation.model_copy(update={"argv": sh('echo \'{"oops":1}\'')})})
    with pytest.raises(OutputSchemaError):
        executor.call(bad, version, {"id": "R-7"})
