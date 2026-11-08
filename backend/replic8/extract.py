"""Extract real function names and lines with tree-sitter (FR-1, FR-11 `parsed` tier).

The model may only choose from these symbols, so it can't invent functions.
COBOL: paragraphs (excluding the entry paragraph). Java: methods (excluding main).
Fortran: subroutines and functions. C: function definitions (not declarations, not main).
Pascal: top-level procedures and functions that have a body. Python, Perl, PHP: top-level
functions, without methods, nested functions or names that start with an underscore.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tree_sitter_language_pack import get_parser

from .guard import Symbol
from .ingest import SKIP_DIRS

SUFFIXES = {
    ".cbl": "cobol", ".cob": "cobol",
    ".java": "java",
    ".f90": "fortran", ".f": "fortran", ".for": "fortran",
    ".c": "c",  # not .h: headers only declare
    ".pas": "pascal", ".pp": "pascal", ".lpr": "pascal",
    ".py": "python",
    ".pl": "perl", ".pm": "perl",
    ".php": "php",
}
# Entry points that run the program rather than one operation.
COBOL_ENTRY = {"MAIN", "MAIN-LOGIC", "MAIN-PARA", "MAIN-PROCEDURE", "BEGIN", "START"}
MAX_FILE_BYTES = 2_000_000
# Some grammars never finish on hostile or garbage input (the COBOL grammar hangs
# on a file containing just "x"). Each file is parsed in its own process with a
# time limit, so a malicious repo can't freeze onboarding (docs/security.md T30).
PARSE_TIMEOUT_S = 10.0
# Each file still gets its own process (one launch costs about 140 ms), but several run at once so a
# repo with hundreds of files does not stall the import.
PARSE_WORKERS = min(8, os.cpu_count() or 2)


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _cobol(tree) -> list[tuple[str, int]]:
    found = []
    for node in _walk(tree.root_node):
        if node.type == "paragraph_header":
            name = node.text.decode("ascii", "replace").strip().rstrip(".").strip()
            if name and name.upper() not in COBOL_ENTRY:
                found.append((name.upper(), node.start_point[0] + 1))
    return found


def _fortran(tree) -> list[tuple[str, int]]:
    found = []
    for node in _walk(tree.root_node):
        if node.type in ("subroutine_statement", "function_statement"):
            for child in node.children:
                if child.type == "name":
                    found.append((child.text.decode("ascii", "replace").lower(), node.start_point[0] + 1))
                    break
    return found


def _java(tree) -> list[tuple[str, int]]:
    found = []
    for node in _walk(tree.root_node):
        if node.type == "method_declaration":
            name = node.child_by_field_name("name")
            if name is not None and name.text != b"main":
                found.append((name.text.decode("ascii", "replace"), name.start_point[0] + 1))
    return found


def _ancestors(node):
    while node.parent is not None:
        node = node.parent
        yield node


def _text(node) -> str:
    return node.text.decode("ascii", "replace")


def _c(tree) -> list[tuple[str, int]]:
    found = []
    for node in _walk(tree.root_node):
        if node.type != "function_definition":
            continue
        decl = node.child_by_field_name("declarator")
        while decl is not None and decl.type != "function_declarator":  # through pointer declarators
            decl = decl.child_by_field_name("declarator")
        name = decl.child_by_field_name("declarator") if decl is not None else None
        if name is not None and name.type == "identifier" and name.text != b"main":
            found.append((_text(name), name.start_point[0] + 1))
    return found


def _pascal(tree) -> list[tuple[str, int]]:
    found = []
    for node in _walk(tree.root_node):
        # defProc has a body; a bare declProc is only an interface declaration. Nested procedures are local helpers.
        if node.type != "defProc" or any(a.type == "defProc" for a in _ancestors(node)):
            continue
        header = node.child_by_field_name("header")
        name = header.child_by_field_name("name") if header is not None else None
        if name is not None and name.type == "identifier":
            found.append((_text(name), name.start_point[0] + 1))
    return found


def _python_params(func) -> list[list]:
    """[name, required] per parameter that a JSON object can fill. *args, **kwargs and separators are skipped."""
    params = func.child_by_field_name("parameters")
    out: list[list] = []
    for child in params.children if params is not None else []:
        if child.type == "identifier":
            out.append([_text(child), True])
        elif child.type == "typed_parameter":
            name = next((c for c in child.children if c.type == "identifier"), None)
            if name is not None:
                out.append([_text(name), True])
        elif child.type in ("default_parameter", "typed_default_parameter"):
            name = child.child_by_field_name("name")
            if name is not None and name.type == "identifier":
                out.append([_text(name), False])
    return out


def _python(tree) -> list[tuple]:
    found = []
    for node in _walk(tree.root_node):
        if node.type != "function_definition":
            continue
        parent = node.parent
        if parent is not None and parent.type == "decorated_definition":
            parent = parent.parent
        if parent is None or parent.type != "module":  # not a method, not nested
            continue
        name = node.child_by_field_name("name")
        if name is not None and not name.text.startswith(b"_") and name.text != b"main":
            found.append((_text(name), name.start_point[0] + 1, _python_params(node)))
    return found


def _perl(tree) -> list[tuple[str, int]]:
    found = []
    for node in _walk(tree.root_node):
        if node.type != "subroutine_declaration_statement":
            continue
        name = node.child_by_field_name("name")
        if name is not None and b"::" not in name.text and not name.text.startswith(b"_"):
            found.append((_text(name), name.start_point[0] + 1))
    return found


def _php(tree) -> list[tuple[str, int]]:
    found = []
    for node in _walk(tree.root_node):
        if node.type != "function_definition" or any(a.type in ("function_definition", "method_declaration") for a in _ancestors(node)):
            continue
        name = node.child_by_field_name("name")
        if name is not None and not name.text.startswith(b"__"):
            found.append((_text(name), name.start_point[0] + 1))
    return found


EXTRACTORS = {"cobol": _cobol, "fortran": _fortran, "java": _java, "c": _c, "pascal": _pascal,
              "python": _python, "perl": _perl, "php": _php}
# What the line that holds the name must look like, per language (the name is escaped into the pattern).
CONFIRM = {
    "c": lambda n: rf"\b{re.escape(n)}\s*\(",
    "pascal": lambda n: rf"\b(function|procedure)\s+{re.escape(n)}\b",
    "python": lambda n: rf"^\s*(async\s+)?def\s+{re.escape(n)}\b",
    "perl": lambda n: rf"^\s*sub\s+{re.escape(n)}\b",
    "php": lambda n: rf"\bfunction\s+&?\s*{re.escape(n)}\s*\(",
}


# A file is a command-line program when it has an entry point that reads its arguments (C main, a Pascal
# `program`, and a script that looks at its argument list). The first such line is the program's "line".
PROGRAM_MARKERS = {
    "c": r"\bmain\s*\(",
    "pascal": r"^\s*program\s+\w+",
    "python": r"__main__|\bargparse\b|\bsys\.argv\b",
    "perl": r"\bARGV\b|\bGetOptions\b",
    "php": r"\$argv\b|\bgetopt\s*\(",
}
MAX_PROGRAMS = 20


def program_symbols(repo_root: Path) -> list[Symbol]:
    """Files that are programs run from a command line. The symbol name is the file name without its suffix."""
    root = repo_root.resolve()
    found: list[Symbol] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(p in SKIP_DIRS for p in rel.parts) or path.is_symlink() or not path.is_file():
            continue
        lang = language_of(path)
        marker = PROGRAM_MARKERS.get(lang or "")
        if marker is None or path.stat().st_size > MAX_FILE_BYTES:
            continue
        name = re.sub(r"[^A-Za-z0-9_]+", "_", path.stem).strip("_")
        if not name or path.suffix.lower() == ".pm":
            continue
        flags = re.I if lang == "pascal" else 0
        for number, text in enumerate(path.read_bytes().decode("utf-8", "replace").splitlines(), start=1):
            if re.search(marker, text, flags) and not text.lstrip().startswith(("//", "#", "/*", "*", "(*")):
                found.append(Symbol(name, rel.as_posix(), number, program=True))
                break
    return found[:MAX_PROGRAMS]


def language_of(path: Path) -> str | None:
    return SUFFIXES.get(path.suffix.lower())


def _confirmed(lines: list[str], name: str, line: int, lang: str) -> bool:
    """The symbol's name must really be on that source line (guards against a confused parse)."""
    if not 1 <= line <= len(lines):
        return False
    text = lines[line - 1]
    if lang == "cobol":
        return text.strip().upper().rstrip(".").strip() == name.upper()
    if lang == "java":
        return f"{name}(" in text.replace(" (", "(")
    pattern = CONFIRM.get(lang)
    if pattern is not None:
        return re.search(pattern(name), text, re.I if lang == "pascal" else 0) is not None
    return name.lower() in text.lower() and ("subroutine" in text.lower() or "function" in text.lower())


def _parse_isolated(lang: str, path: Path, timeout_s: float) -> tuple[list[tuple[str, int, tuple]], bool] | None:
    """Parse one file in a child process. Returns ([(name, line, params)], has_error), or None if it timed out or crashed."""
    try:
        proc = subprocess.run([sys.executable, "-m", "replic8.extract", lang, str(path)],
                              capture_output=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
        return [(str(item[0]), int(item[1]), tuple((str(p), bool(r)) for p, r in (item[2] if len(item) > 2 else [])))
                for item in data["symbols"]], bool(data["has_error"])
    except (ValueError, KeyError, TypeError):
        return None


def extract_symbols(repo_root: Path, timeout_s: float = PARSE_TIMEOUT_S) -> tuple[list[Symbol], list[str]]:
    """Return (symbols, partly_parsed_files).

    Grammars don't cover every legacy dialect. When a file has parse errors we still
    keep the symbols the parser did read, but only after confirming each name is on
    its reported line, and we report the file so the UI can flag it. A file whose
    parse times out or crashes is reported too, with no symbols taken from it.
    """
    root = repo_root.resolve()
    candidates: list[tuple[Path, Path, str]] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(p in SKIP_DIRS for p in rel.parts) or path.is_symlink() or not path.is_file():
            continue
        lang = language_of(path)
        if lang is None or path.stat().st_size > MAX_FILE_BYTES:
            continue
        candidates.append((rel, path, lang))
    with ThreadPoolExecutor(max_workers=PARSE_WORKERS) as pool:
        results = list(pool.map(lambda c: _parse_isolated(c[2], c[1], timeout_s), candidates))  # keeps file order

    symbols: list[Symbol] = []
    errors: list[str] = []
    for (rel, path, lang), parsed in zip(candidates, results):
        if parsed is None:
            errors.append(rel.as_posix())
            continue
        pairs, has_error = parsed
        if has_error:
            errors.append(rel.as_posix())
        lines = path.read_bytes().decode("utf-8", "replace").splitlines()
        symbols.extend(Symbol(name, rel.as_posix(), line, params) for name, line, params in pairs
                       if _confirmed(lines, name, line, lang))
    return symbols, errors


def _main(argv: list[str]) -> int:
    """Child process entry: python -m replic8.extract <language> <file>."""
    lang, file = argv
    if lang not in EXTRACTORS:
        return 2
    tree = get_parser(lang).parse(Path(file).read_bytes())
    print(json.dumps({"has_error": tree.root_node.has_error, "symbols": EXTRACTORS[lang](tree)}))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
