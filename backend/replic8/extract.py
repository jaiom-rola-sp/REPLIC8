"""Extract real function names and lines with tree-sitter (FR-1, FR-11 `parsed` tier).

The model may only choose from these symbols, so it can't invent functions.
COBOL: paragraphs (excluding the entry paragraph). Fortran: subroutines and functions.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter_language_pack import get_parser

from .guard import Symbol
from .ingest import SKIP_DIRS

SUFFIXES = {
    ".cbl": "cobol", ".cob": "cobol",
    ".f90": "fortran", ".f": "fortran", ".for": "fortran",
}
# Entry points that run the program rather than one operation.
COBOL_ENTRY = {"MAIN", "MAIN-LOGIC", "MAIN-PARA", "MAIN-PROCEDURE", "BEGIN", "START"}
MAX_FILE_BYTES = 2_000_000


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


def language_of(path: Path) -> str | None:
    return SUFFIXES.get(path.suffix.lower())


def _confirmed(lines: list[str], name: str, line: int, lang: str) -> bool:
    """The symbol's name must really be on that source line (guards against a confused parse)."""
    if not 1 <= line <= len(lines):
        return False
    text = lines[line - 1]
    if lang == "cobol":
        return text.strip().upper().rstrip(".").strip() == name.upper()
    return name.lower() in text.lower() and ("subroutine" in text.lower() or "function" in text.lower())


def extract_symbols(repo_root: Path) -> tuple[list[Symbol], list[str]]:
    """Return (symbols, partly_parsed_files).

    Grammars don't cover every legacy dialect. When a file has parse errors we still
    keep the symbols the parser did read, but only after confirming each name is on
    its reported line, and we report the file so the UI can flag it.
    """
    root = repo_root.resolve()
    symbols: list[Symbol] = []
    errors: list[str] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(p in SKIP_DIRS for p in rel.parts) or path.is_symlink() or not path.is_file():
            continue
        lang = language_of(path)
        if lang is None or path.stat().st_size > MAX_FILE_BYTES:
            continue
        source = path.read_bytes()
        tree = get_parser(lang).parse(source)
        if tree.root_node.has_error:
            errors.append(rel.as_posix())
        lines = source.decode("utf-8", "replace").splitlines()
        pairs = _cobol(tree) if lang == "cobol" else _fortran(tree)
        symbols.extend(Symbol(name, rel.as_posix(), line) for name, line in pairs
                       if _confirmed(lines, name, line, lang))
    return symbols, errors
