"""Function finding for C, Pascal, Python, Perl and PHP (FR-11, `parsed` tier).

Each case writes a small repo and runs the real extraction (one child process per file), then checks the exact
names and line numbers. The trap cases matter as much as the finds: declarations, methods, nested functions,
internal helpers and entry points must not be offered as operations.
"""

import pytest

from replic8.extract import extract_symbols, language_of
from pathlib import Path

CASES = {
    "c": ("orders.c", """#include <stdio.h>
static int helper(void) { return 1; }
char *get_name(int x, const char *s) { return 0; }
int old_style(a, b) int a; int b; { return a + b; }
int decl_only(int);
int main(int argc, char **argv) { return 0; }
""", {"helper": 2, "get_name": 3, "old_style": 4}),
    "pascal": ("pay.pas", """unit Pay;
interface
function Gross(h: Integer): Integer;
procedure Report;
implementation
function Gross(h: Integer): Integer;
  function Rate: Integer;
  begin
    Rate := 20;
  end;
begin
  Gross := h * Rate;
end;
procedure Report;
begin
  WriteLn('x');
end;
end.
""", {"Gross": 6, "Report": 14}),
    "python": ("billing.py", """import os
def public(a, b=1):
    def inner():
        return 1
    return a
@decorator
def decorated(x):
    return x
async def aio(x):
    return x
def _private():
    pass
def main():
    pass
class K:
    def method(self):
        pass
if __name__ == '__main__':
    main()
""", {"public": 2, "decorated": 7, "aio": 9}),
    "perl": ("report.pl", """package Billing;
sub get_vendor { my ($p) = @_; return 'ACME'; }
sub _helper { 1 }
sub Other::qualified { 2 }
BEGIN { 1 }
1;
""", {"get_vendor": 2}),
    "php": ("catalog.php", """<?php
function get_item($sku) { return 1; }
class C { public function method() {} }
function &by_ref($x) {
    function nested() { return 1; }
    return $x;
}
function __magic() { return 1; }
""", {"get_item": 2, "by_ref": 4}),
}


@pytest.mark.parametrize("language", sorted(CASES))
def test_finds_the_real_functions_and_only_those(tmp_path, language):
    name, source, expected = CASES[language]
    (tmp_path / name).write_text(source)
    symbols, partly_parsed = extract_symbols(tmp_path)
    assert {s.name: s.line for s in symbols} == expected, [(s.name, s.line) for s in symbols]
    assert all(s.file == name for s in symbols)
    assert partly_parsed == []


@pytest.mark.parametrize("language,broken", [("python", "def (:\n"), ("php", "<?php\nfunction (\n"), ("perl", "sub {\n"), ("c", "int f( {\n")])
def test_a_file_that_does_not_parse_is_reported_not_trusted(tmp_path, language, broken):
    name = CASES[language][0]
    (tmp_path / name).write_text(broken)
    symbols, partly_parsed = extract_symbols(tmp_path)
    assert symbols == [] and partly_parsed == [name]


def test_every_language_resolves_from_its_file_extension():
    for file, language in {"a.c": "c", "a.pas": "pascal", "a.pp": "pascal", "a.lpr": "pascal", "a.py": "python",
                           "a.pl": "perl", "a.pm": "perl", "a.php": "php", "A.PY": "python"}.items():
        assert language_of(Path(file)) == language, file
    assert language_of(Path("orders.h")) is None      # headers only declare
    assert language_of(Path("a.rb")) is None


def test_a_name_is_only_trusted_when_it_is_on_the_reported_line():
    from replic8.extract import _confirmed
    assert _confirmed(["def get_part(part_id):"], "get_part", 1, "python")
    assert not _confirmed(["def other(x):"], "get_part", 1, "python")
    assert not _confirmed(["# def get_part(x):"], "get_part", 1, "python")       # a comment is not a definition
    assert _confirmed(["char *get_name(int x)"], "get_name", 1, "c")
    assert _confirmed(["function Gross(h: Integer): Integer;"], "gross", 1, "pascal")   # Pascal ignores case
    assert _confirmed(["sub get_vendor {"], "get_vendor", 1, "perl")
    assert _confirmed(["function &by_ref($x) {"], "by_ref", 1, "php")
    assert not _confirmed(["x = 1"], "x", 5, "c")                                # a line number that does not exist


def test_many_files_are_parsed_in_parallel_but_reported_in_file_order(tmp_path):
    for i in (7, 2, 11, 5, 0, 9, 3, 1, 10, 4, 8, 6):
        (tmp_path / f"mod_{i:02d}.py").write_text(f"def func_{i}(a):\n    return a\n")
    (tmp_path / "mod_03.py").write_text("def (:\n")                       # one broken file among them
    symbols, partly_parsed = extract_symbols(tmp_path)
    assert [s.file for s in symbols] == sorted(s.file for s in symbols)
    assert len(symbols) == 11 and partly_parsed == ["mod_03.py"]
