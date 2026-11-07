"""Run legacy code inside a locked-down Docker container (FR-4).

Legacy code is untrusted. Each call gets a fresh container with:
no network, read-only root filesystem, all capabilities dropped, no privilege
escalation, a non-root user, CPU/memory/PID limits, a wall-clock timeout,
and a cap on output size. Caller input goes in on stdin as JSON, never as argv.
"""

from __future__ import annotations

import re
import subprocess
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import SandboxLimits

SAFE_PATH = re.compile(r"^[A-Za-z0-9_./-]+$")
STDERR_KEEP = 4096


class SandboxError(Exception):
    pass


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


def build_command(name: str, image: str, code_dir: Path, argv: list[str], limits: SandboxLimits) -> list[str]:
    return [
        "docker", "run", "--rm", "-i", "--init",
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
        "--mount", f"type=bind,source={code_dir},target=/app,readonly",
        "--workdir", "/app",
        "--log-driver", "none",
        image,
        *argv,
    ]


class Sandbox:
    def __init__(self, repos_root: Path, allowed_images: frozenset[str], limits: SandboxLimits):
        self.repos_root = repos_root.resolve()
        self.allowed_images = allowed_images
        self.limits = limits

    def _check(self, image: str, code_dir: Path, payload: bytes) -> Path:
        if image not in self.allowed_images:
            raise SandboxError("image is not on the sandbox allowlist")
        resolved = code_dir.resolve()
        if self.repos_root not in resolved.parents or not resolved.is_dir():
            raise SandboxError("code directory must be a cloned repo under the data dir")
        if not SAFE_PATH.match(str(resolved)):
            raise SandboxError("code directory path has unsafe characters")
        if len(payload) > self.limits.max_input_bytes:
            raise SandboxError("input too large")
        return resolved

    def run(self, image: str, code_dir: Path, argv: list[str], payload: bytes) -> SandboxResult:
        resolved = self._check(image, code_dir, payload)
        name = f"replic8-{uuid.uuid4().hex}"
        cmd = build_command(name, image, resolved, argv, self.limits)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        limit = self.limits.max_output_bytes
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
            proc.wait(timeout=self.limits.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill(name, proc)
            proc.wait(timeout=10)
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
