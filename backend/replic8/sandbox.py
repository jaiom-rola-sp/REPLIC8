"""Run legacy code inside a locked-down Docker container (FR-4).

Legacy code is untrusted. Each call gets a fresh container with:
no network, read-only root filesystem, all capabilities dropped, no privilege
escalation, a non-root user, CPU/memory/PID limits, a wall-clock timeout,
and a cap on output size. Caller input goes in on stdin as JSON, never as argv.
Images must be pinned by digest and are never pulled at call time.
"""

from __future__ import annotations

import re
import subprocess
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import PINNED_IMAGE, SandboxLimits

# Linux/macOS paths, or Windows paths like C:\\Users\\aryan\\data (a literal "~" folder is
# allowed too). No commas, quotes or spaces, which could break the --mount spec.
SAFE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/])?[A-Za-z0-9_./\\~-]+$")
STDERR_KEEP = 4096


class SandboxError(Exception):
    """Base error for running legacy code (PRD section 7). Messages are safe to show:
    they never include legacy stderr, stack traces, or caller input."""

    status = 502

    def __init__(self, message: str = "legacy system returned an error"):
        super().__init__(message)


class SandboxTimeout(SandboxError):
    status = 504


class SandboxCrash(SandboxError):
    """The legacy program failed, or returned output that isn't valid JSON."""


class OutputSchemaError(SandboxError):
    """The legacy program answered, but not in the published output schema. Triggers self-heal."""


class FunctionMissing(SandboxError):
    """The legacy program no longer has the called function (e.g. it was renamed). Triggers self-heal."""


# Exit codes from runtime/shim.py
SHIM_FUNCTION_MISSING = 3
SHIM_VALUE_REFUSED = 4  # call_cli.py refused a caller value (the caller's fault, not the legacy program's)


@dataclass
class SandboxResult:
    exit_code: int | None
    stdout: bytes
    stderr_tail: str
    timed_out: bool
    output_too_large: bool

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.output_too_large


def build_command(name: str, image: str, code_dir: Path, argv: list[str], limits: SandboxLimits,
                  build_dir: Path | None = None, writable_build: bool = False) -> list[str]:
    mounts = ["--mount", f"type=bind,source={code_dir},target=/app,readonly"]
    if build_dir is not None:
        ro = "" if writable_build else ",readonly"
        mounts += ["--mount", f"type=bind,source={build_dir},target=/build{ro}"]
    return [
        "docker", "run", "--rm", "-i", "--init",
        "--pull", "never",
        "--name", name,
        "--network", "none",
        "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16m",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", str(limits.pids),
        "--memory", limits.memory,
        "--memory-swap", limits.memory,
        "--cpus", limits.cpus,
        "--ulimit", "nofile=256:256",
        "--user", "65534:65534",
        *mounts,
        "--workdir", "/app",
        "--log-driver", "none",
        image,
        *argv,
    ]


# Compiling needs more memory and time than a lookup. Still no network.
BUILD_LIMITS = SandboxLimits(timeout_s=180.0, memory="1g", cpus="1.0", pids=128,
                             max_output_bytes=100_000, max_input_bytes=0)


class Sandbox:
    def __init__(self, repos_root: Path, allowed_images: frozenset[str], limits: SandboxLimits,
                 builds_root: Path | None = None):
        unpinned = sorted(i for i in allowed_images if not PINNED_IMAGE.match(i))
        if unpinned:
            raise SandboxError(f"sandbox images must be pinned by digest: {unpinned}")
        self.repos_root = repos_root.resolve()
        self.builds_root = (builds_root or repos_root.parent / "builds").resolve()
        self.allowed_images = allowed_images
        self.limits = limits

    def _check_build_dir(self, build_dir: Path) -> Path:
        resolved = build_dir.resolve()
        if self.builds_root not in resolved.parents or not resolved.is_dir():
            raise SandboxError("build directory must be under the builds dir")
        if not SAFE_PATH.match(str(resolved)):
            raise SandboxError("build directory path has unsafe characters")
        return resolved

    def build(self, image: str, code_dir: Path, build_dir: Path, argv: list[str]) -> SandboxResult:
        """Compile legacy code. Only /build is writable; output goes there."""
        build_dir.mkdir(parents=True, exist_ok=True)
        build_dir.chmod(0o777)  # the container runs as nobody (65534)
        return self.run(image, code_dir, argv, b"", build_dir=build_dir, writable_build=True,
                        limits=BUILD_LIMITS)

    def pinned(self, image: str) -> str:
        """The digest-pinned reference to run for `image`.

        Operations name an image like `replic8-legacy-runtime:1`; the allowlist holds
        its pinned form (`replic8-legacy-runtime:1@sha256:...`), which is what runs.
        """
        if image in self.allowed_images:
            return image
        for allowed in sorted(self.allowed_images):
            if allowed.split("@", 1)[0] == image:
                return allowed
        raise SandboxError("image is not on the sandbox allowlist")

    def _check(self, image: str, code_dir: Path, payload: bytes) -> Path:
        resolved = code_dir.resolve()
        if self.repos_root not in resolved.parents or not resolved.is_dir():
            raise SandboxError("code directory must be a cloned repo under the data dir")
        if not SAFE_PATH.match(str(resolved)):
            raise SandboxError("code directory path has unsafe characters")
        if len(payload) > self.limits.max_input_bytes:
            raise SandboxError("input too large")
        return resolved

    def run(self, image: str, code_dir: Path, argv: list[str], payload: bytes,
            build_dir: Path | None = None, writable_build: bool = False,
            limits: SandboxLimits | None = None) -> SandboxResult:
        limits = limits or self.limits
        image = self.pinned(image)
        resolved = self._check(image, code_dir, payload)
        build = self._check_build_dir(build_dir) if build_dir is not None else None
        name = f"replic8-{uuid.uuid4().hex}"
        cmd = build_command(name, image, resolved, argv, limits, build, writable_build)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        limit = limits.max_output_bytes
        out = bytearray()
        err = bytearray()
        too_large = threading.Event()

        def read_stdout() -> None:
            assert proc.stdout is not None
            while chunk := proc.stdout.read(65536):
                if too_large.is_set():
                    continue  # keep draining so the docker client never blocks
                if len(out) + len(chunk) > limit:
                    too_large.set()
                    threading.Thread(target=_kill, args=(name, proc), daemon=True).start()
                    continue
                out.extend(chunk)
            proc.stdout.close()

        def read_stderr() -> None:
            assert proc.stderr is not None
            while chunk := proc.stderr.read(65536):
                err.extend(chunk)
                del err[:-STDERR_KEEP]
            proc.stderr.close()

        def write_stdin() -> None:
            assert proc.stdin is not None
            try:
                proc.stdin.write(payload)
                proc.stdin.close()
            except (BrokenPipeError, ValueError):
                pass

        threads = [threading.Thread(target=f, daemon=True) for f in (read_stdout, read_stderr, write_stdin)]
        for t in threads:
            t.start()
        timed_out = False
        try:
            proc.wait(timeout=limits.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill(name, proc)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass  # docker client is stuck even after kill; report exit_code=None, timed_out=True
        for t in threads:
            t.join(timeout=5)

        return SandboxResult(
            exit_code=proc.returncode,
            stdout=bytes(out),
            stderr_tail=err.decode("utf-8", "replace"),
            timed_out=timed_out,
            output_too_large=too_large.is_set(),
        )


def _kill(name: str, proc: subprocess.Popen) -> None:
    """Stop the container itself; killing only the docker client would leave it running."""
    try:
        subprocess.run(["docker", "kill", name], capture_output=True, timeout=15)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
    finally:
        proc.kill()
