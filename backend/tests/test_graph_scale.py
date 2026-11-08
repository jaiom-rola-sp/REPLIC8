"""The graph must stay small when many operations share common field names (an "id" matches everywhere)."""

from conftest import COMMIT, make_op, passed
from replic8 import graph
from replic8.graph import build_graph
from replic8.models import WrapperVersion

SYSTEMS = ("alpha", "beta", "gamma")


class FakeRegistry:
    def __init__(self, per_system: int):
        self.versions = {}
        for system in SYSTEMS:
            ops = [make_op(f"op_{i}", ns=system) for i in range(per_system)]  # every op takes and returns "id"
            self.versions[system] = WrapperVersion(
                system=system, version=1, source_commit=COMMIT, repo_url=f"https://github.com/o/{system}",
                operations=ops, tests={op.tool: passed() for op in ops})

    def systems(self):
        return list(self.versions)

    def current(self, system):
        return self.versions[system]


def test_system_links_stay_one_entry_per_pair_however_many_operations_match():
    result = build_graph(FakeRegistry(per_system=10))
    assert len(result["system_links"]) == 6                      # 3 systems -> 6 ordered pairs
    one = next(l for l in result["system_links"] if (l["source"], l["target"]) == ("alpha", "beta"))
    assert one["fields"] == ["id"] and one["operation_pairs"] == 100 and one["evidence"] == "schema"
    assert len(result["edges"]) >= 600 and result["truncated"] is False


def test_operation_edges_are_capped_but_the_summary_is_complete(monkeypatch):
    monkeypatch.setattr(graph, "MAX_DATA_EDGES", 50)
    result = build_graph(FakeRegistry(per_system=10))
    assert len([e for e in result["edges"] if e["type"] == "data"]) == 50
    assert result["truncated"] is True
    assert len(result["system_links"]) == 6 and all(l["operation_pairs"] == 100 for l in result["system_links"])


def test_a_larger_registry_is_still_cheap():
    import time
    start = time.time()
    result = build_graph(FakeRegistry(per_system=60))            # 180 operations, 32,400 matching pairs
    assert time.time() - start < 5
    assert len([e for e in result["edges"] if e["type"] == "data"]) == graph.MAX_DATA_EDGES
    assert result["truncated"] is True and len(result["system_links"]) == 6
