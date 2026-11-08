import io
import shutil
import subprocess

import pytest

from replic8 import sandbox as sandbox_module
from replic8.config import ConfigError, SandboxLimits, Settings
from replic8.executor import CallError, Executor
from replic8.models import WrapperVersion
from replic8.sandbox import Sandbox, SandboxError, build_command

from conftest import COMMIT, make_op, passed

TAG = "alpine:3.20"
FAKE_PINNED = TAG + "@sha256:" + "0" * 64


def _local_digest() -> str | None:
    """The pinned reference (alpine@sha256:...) of a locally pulled alpine:3.20, if Docker has one."""
    if not shutil.which("docker"):
        return None
    r = subprocess.run(["docker", "image", "inspect", TAG, "--format", "{{index .RepoDigests 0}}"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 and "@sha256:" in r.stdout else None


DIGEST = _local_digest()
IMAGE = DIGEST or FAKE_PINNED


def test_command_has_every_hardening_flag(tmp_path):
    cmd = build_command("n", IMAGE, tmp_path, ["echo", "hi"], SandboxLimits())
    joined = " ".join(cmd)
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "--security-opt no-new-privileges",
                 "--pids-limit", "--memory 256m", "--user 65534:65534", "readonly", "--log-driver none"):
        assert flag in joined
    assert cmd[-3:] == [IMAGE, "echo", "hi"]


def test_command_never_pulls_images(tmp_path):
    cmd = build_command("n", IMAGE, tmp_path, ["true"], SandboxLimits())
    i = cmd.index("--pull")
    assert cmd[i + 1] == "never"
    assert i < cmd.index(IMAGE)  # an option, not an argument to the legacy program


def test_images_must_be_pinned_by_digest(tmp_path):
    with pytest.raises(SandboxError, match="digest"):
        Sandbox(tmp_path, frozenset({TAG}), SandboxLimits())
    with pytest.raises(SandboxError):
        Sandbox(tmp_path, frozenset({FAKE_PINNED, "alpine@sha256:short"}), SandboxLimits())
    Sandbox(tmp_path, frozenset({FAKE_PINNED, "alpine@sha256:" + "a" * 64}), SandboxLimits())

    with pytest.raises(ConfigError, match="digest"):
        Settings(data_dir=tmp_path, sandbox_images=frozenset({TAG})).validate()
    Settings(data_dir=tmp_path, sandbox_images=frozenset({FAKE_PINNED})).validate()


class StuckDockerClient:
    """A docker client that never exits, even after it is killed."""

    def __init__(self, *args, **kwargs):
        self.stdin, self.stdout, self.stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()
        self.returncode = None

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired("docker", timeout)

    def kill(self):
        pass


def test_stuck_client_after_timeout_is_reported_not_raised(tmp_path, monkeypatch):
    killed = []
    monkeypatch.setattr(sandbox_module.subprocess, "Popen", StuckDockerClient)
    monkeypatch.setattr(sandbox_module, "_kill", lambda name, proc: killed.append(name))
    monkeypatch.setattr(Sandbox, "_check", lambda self, image, code_dir, payload: code_dir)
    box = Sandbox(tmp_path, frozenset({FAKE_PINNED}), SandboxLimits(timeout_s=0.01))

    result = box.run(FAKE_PINNED, tmp_path, ["sleep", "60"], b"{}")

    assert killed, "the container should still be killed"
    assert result.timed_out and result.exit_code is None and not result.ok


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


docker = pytest.mark.skipif(DIGEST is None, reason=f"needs Docker with {TAG} pulled")


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
    with pytest.raises(CallError, match="schema"):
        executor.call(bad, version, {"id": "R-7"})
