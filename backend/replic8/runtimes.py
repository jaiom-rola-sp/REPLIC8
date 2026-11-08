"""How REPLIC8 builds and calls code in each supported legacy language.

Everything here is chosen by REPLIC8, never by the model: the image, the build
command, and the command that calls one function through the shim.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .extract import language_of
from .guard import Symbol

LEGACY_IMAGE = "replic8-legacy-runtime:1"
SYMBOL = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class Runtime:
    language: str
    image: str
    build_argv: tuple[str, ...]


RUNTIMES = {
    "cobol": Runtime("cobol", LEGACY_IMAGE, ("python3", "/replic8/build.py")),
    "fortran": Runtime("fortran", LEGACY_IMAGE, ("python3", "/replic8/build.py")),
    "java": Runtime("java", LEGACY_IMAGE, ("python3", "/replic8/build.py")),
    "c": Runtime("c", LEGACY_IMAGE, ("python3", "/replic8/build.py")),
    "pascal": Runtime("pascal", LEGACY_IMAGE, ("python3", "/replic8/build.py")),
    "python": Runtime("python", LEGACY_IMAGE, ("python3", "/replic8/build.py")),
    "perl": Runtime("perl", LEGACY_IMAGE, ("python3", "/replic8/build.py")),
    "php": Runtime("php", LEGACY_IMAGE, ("python3", "/replic8/build.py")),
}


# Languages whose programs speak the line protocol through the shim. C, Pascal, Python, Perl and PHP build
# and run, but they are called another way (the Python caller and the command-line wrapper), so the protocol
# command must never be built for them.
PROTOCOL = {"cobol", "fortran", "java"}


def argv_for(symbol: str, file: str) -> list[str]:
    """Command that calls `symbol` defined in `file`. Empty list means "can't call it"."""
    lang = language_of(PurePosixPath(file))
    if lang not in PROTOCOL or not SYMBOL.match(symbol):
        return []
    if lang == "java":
        # All Java sources build into one jar (runtime/build.py).
        return ["python3", "/replic8/shim.py", "/build/app.jar", symbol]
    binary = PurePosixPath(file).stem.lower()
    if not re.fullmatch(r"[a-z0-9_-]{1,64}", binary):
        return []
    return ["python3", "/replic8/shim.py", f"/build/{binary}", symbol]


def callable_symbols(repo_root: Path, symbols: list[Symbol]) -> list[Symbol]:
    """Keep symbols the program accepts as commands under the legacy line protocol.

    The demo programs dispatch on the command name as a quoted literal
    (COBOL `WHEN "GET-REQUEST"`, Java `"checkStock".equalsIgnoreCase(cmd)`). Internal
    helpers such as READ-INPUT or findPart never appear that way, so they aren't offered.
    Contract tests are still the real gate.
    """
    root = repo_root.resolve()
    texts: dict[str, str] = {}
    kept = []
    for sym in symbols:
        if sym.file not in texts:
            path = (root / sym.file).resolve()
            texts[sym.file] = path.read_text(errors="replace").upper() if root in path.parents else ""
        name = sym.name.upper()
        if f'"{name}"' in texts[sym.file] or f"'{name}'" in texts[sym.file]:
            kept.append(sym)
    return kept


def pin_local_image(image: str = LEGACY_IMAGE) -> str:
    """The digest-pinned reference of a locally built image (`name:tag@sha256:...`).

    Uses the registry digest if the image has one, otherwise the local image digest
    (Docker's containerd image store accepts either with `--pull never`).
    """
    out = subprocess.run(["docker", "image", "inspect", image, "--format",
                          "{{range .RepoDigests}}{{println .}}{{end}}|{{.Id}}"],
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError(f"image {image} not found; build it first (docker build -t {image} backend/runtime)")
    repo_digests, _, image_id = out.stdout.strip().rpartition("|")
    for line in repo_digests.split():
        if "@sha256:" in line:
            return f"{image}@{line.split('@', 1)[1]}"
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id.strip()):
        raise RuntimeError(f"could not read the digest of {image}")
    return f"{image}@{image_id.strip()}"
