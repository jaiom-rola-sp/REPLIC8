import json

import pytest

from replic8.guard import Symbol, decide_access, validate_proposal
from replic8.models import Access, Tier

IMAGE = "python:3.12-alpine"


def argv_for(symbol, file):
    return ["python", "/replic8/shim.py", file, symbol]


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "maint.py").write_text("\n".join(f"line {i}" for i in range(1, 21)))
    return tmp_path


def proposal(**overrides):
    op = {
        "name": "get_request", "symbol": "get_request", "file": "src/maint.py", "line": 3,
        "access": "read", "description": "Look up a request",
        "input_schema": {"type": "object"}, "output_schema": {"type": "object"},
    }
    op.update(overrides)
    return json.dumps({"operations": [op]})


SYMBOLS = [Symbol("get_request", "src/maint.py", 3), Symbol("deleteRequest", "src/maint.py", 9)]


def test_accepts_operation_matching_extracted_symbol(repo):
    ok, bad = validate_proposal(proposal(), namespace="maintenance", tier=Tier.parsed,
                                repo_root=repo, image=IMAGE, argv_for=argv_for, symbols=SYMBOLS)
    assert [o.tool for o in ok] == ["maintenance.get_request"] and bad == {}
    assert ok[0].invocation.image == IMAGE
    assert ok[0].invocation.argv == ["python", "/replic8/shim.py", "src/maint.py", "get_request"]


def test_model_cannot_supply_a_command(repo):
    with pytest.raises(ValueError):
        validate_proposal(proposal(argv=["sh", "-c", "curl evil"]), namespace="maintenance", tier=Tier.parsed,
                          repo_root=repo, image=IMAGE, argv_for=argv_for, symbols=SYMBOLS)


def test_shell_command_from_builder_is_refused(repo):
    ok, bad = validate_proposal(proposal(), namespace="maintenance", tier=Tier.parsed, repo_root=repo,
                                image=IMAGE, argv_for=lambda s, f: ["/bin/sh", "-c", s], symbols=SYMBOLS)
    assert ok == [] and "safe command" in bad["maintenance.get_request"]


def test_rejects_hallucinated_symbol(repo):
    ok, bad = validate_proposal(proposal(symbol="get_everything", line=4), namespace="maintenance",
                                tier=Tier.parsed, repo_root=repo, image=IMAGE, argv_for=argv_for, symbols=SYMBOLS)
    assert ok == [] and "extracted symbol" in bad["maintenance.get_request"]


@pytest.mark.parametrize("file,line", [("src/maint.py", 999), ("src/missing.py", 1), ("../../etc/passwd", 1)])
def test_inferred_tier_needs_real_location(repo, file, line):
    ok, bad = validate_proposal(proposal(file=file, line=line), namespace="maintenance",
                                tier=Tier.inferred, repo_root=repo, image=IMAGE, argv_for=argv_for)
    assert ok == [] and bad


def test_model_cannot_label_a_write_function_as_read(repo):
    ok, _ = validate_proposal(proposal(name="delete_request", symbol="deleteRequest", line=9),
                              namespace="maintenance", tier=Tier.parsed, repo_root=repo,
                              image=IMAGE, argv_for=argv_for, symbols=SYMBOLS)
    assert ok[0].access is Access.write


@pytest.mark.parametrize("name,claimed,expected", [
    ("get_request", "read", Access.read),
    ("getRequest", "write", Access.write),
    ("updatePart", "read", Access.write),
    ("SUBMIT_ORDER", "read", Access.write),
    ("check_stock", "read", Access.read),
])
def test_decide_access(name, claimed, expected):
    assert decide_access(name, claimed) is expected


@pytest.mark.parametrize("raw", [
    "not json",
    json.dumps({"operations": [], "run_shell": "rm -rf /"}),
    json.dumps({"operations": [{"name": "x"}]}),
    proposal(extra_field="ignore previous instructions"),
])
def test_rejects_malformed_or_extra_fields(repo, raw):
    with pytest.raises(ValueError):
        validate_proposal(raw, namespace="maintenance", tier=Tier.inferred, repo_root=repo, image=IMAGE, argv_for=argv_for)
