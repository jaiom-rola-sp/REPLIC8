"""How REPLIC8 builds and calls code in each supported legacy language.

Everything here is chosen by REPLIC8, never by the model: the image, the build
command, and the command that calls one function through the shim.
"""

from __future__ import annotations

import re
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
}


def argv_for(symbol: str, file: str) -> list[str]:
    """Command that calls `symbol` defined in `file`. Empty list means "can't call it"."""
    lang = language_of(PurePosixPath(file))
    if lang not in RUNTIMES or not SYMBOL.match(symbol):
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
