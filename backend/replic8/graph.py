"""Graph of systems, operations and the data links between them (FR-6).

Data edges come only from real field names, never from model opinion (PRD
section 8): an edge A -> B means a field that operation A returns (in its
published output schema or its recorded contract outputs) has the same name
and a compatible type as an input field of operation B in another system.

The result also carries `system_links` (one compact entry per pair of systems: the shared fields, the
strongest evidence, and how many operation pairs matched) and `truncated` (true when `edges` hit the cap).
"""

from __future__ import annotations

from typing import Any

from .models import Access, Operation, WrapperVersion
from .registry import Registry

JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}

# Operation-to-operation links grow with the square of the operation count (a field like "id" can match
# everywhere), so the list is capped. `system_links` has one entry per pair of systems and stays small.
MAX_DATA_EDGES = 2000


def _schema_fields(schema: dict[str, Any]) -> dict[str, set[str]]:
    fields: dict[str, set[str]] = {}
    for name, spec in (schema.get("properties") or {}).items():
        if isinstance(spec, dict):
            t = spec.get("type")
            fields.setdefault(name, set()).update(t if isinstance(t, list) else [t] if t else [])
            if spec.get("type") == "array" and isinstance(spec.get("items"), dict):
                for sub, types in _schema_fields(spec["items"]).items():
                    fields.setdefault(sub, set()).update(types)
    return fields


def _observed_fields(value: Any, out: dict[str, set[str]]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                _observed_fields(item, out)
            elif type(item) in JSON_TYPES:
                out.setdefault(key, set()).add(JSON_TYPES[type(item)])
    elif isinstance(value, list):
        for item in value:
            _observed_fields(item, out)


def output_fields(op: Operation, version: WrapperVersion) -> dict[str, tuple[set[str], str]]:
    """field -> (types, evidence). Evidence is 'recorded' when seen in a real contract output."""
    result = {k: (v, "schema") for k, v in _schema_fields(op.output_schema).items()}
    observed: dict[str, set[str]] = {}
    for case in version.cases.get(op.tool, []):
        _observed_fields(case.output, observed)
    for k, v in observed.items():
        result[k] = (result.get(k, (set(), ""))[0] | v, "recorded")
    return result


def _compatible(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    numeric = {"integer", "number"}
    return bool(a & b) or (bool(a & numeric) and bool(b & numeric))


def build_graph(registry: Registry, write_allowlist: frozenset[str] = frozenset()) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [{"id": "gateway", "type": "gateway", "label": "REPLIC8"}]
    edges: list[dict[str, Any]] = []
    live: list[tuple[Operation, WrapperVersion]] = []
    for system in registry.systems():
        version = registry.current(system)
        if version is None:
            continue
        nodes.append({"id": f"system:{system}", "type": "system", "label": system, "version": version.version,
                      "source_commit": version.source_commit, "repo": version.repo_url,
                      "operations": len(version.operations)})
        edges.append({"id": f"gateway->{system}", "source": "gateway", "target": f"system:{system}",
                      "type": "registered"})
        for op in version.operations:
            nodes.append({"id": op.tool, "type": "operation", "label": op.tool, "system": system,
                          "access": op.access.value, "tier": op.tier.value, "source": str(op.source),
                          "enabled": op.access is Access.read or op.tool in write_allowlist})
            edges.append({"id": f"{system}->{op.tool}", "source": f"system:{system}", "target": op.tool,
                          "type": "provides"})
            live.append((op, version))

    inputs = {op.tool: _schema_fields(op.input_schema) for op, _ in live}
    links: dict[tuple[str, str], dict[str, Any]] = {}
    drawn = 0
    truncated = False
    for out_op, out_ver in live:
        produced = output_fields(out_op, out_ver)
        for in_op, _ in live:
            if in_op.namespace == out_op.namespace:
                continue
            matched = [(field, produced[field][1]) for field, types in inputs[in_op.tool].items()
                       if field in produced and _compatible(produced[field][0], types)]
            if not matched:
                continue
            link = links.setdefault((out_op.namespace, in_op.namespace), {
                "source": out_op.namespace, "target": in_op.namespace, "fields": set(),
                "evidence": "schema", "operation_pairs": 0})
            link["operation_pairs"] += 1
            for field, evidence in matched:
                link["fields"].add(field)
                if evidence == "recorded":
                    link["evidence"] = "recorded"
                if drawn < MAX_DATA_EDGES:
                    drawn += 1
                    edges.append({"id": f"{out_op.tool}->{in_op.tool}:{field}", "source": out_op.tool,
                                  "target": in_op.tool, "type": "data", "field": field, "evidence": evidence})
                else:
                    truncated = True
    system_links = [{**link, "fields": sorted(link["fields"])} for _, link in sorted(links.items())]
    return {"nodes": nodes, "edges": edges, "system_links": system_links, "truncated": truncated}
