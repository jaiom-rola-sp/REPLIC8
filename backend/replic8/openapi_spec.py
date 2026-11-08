"""Read a modern system's OpenAPI file and list its operations (FR-15).

This only reads a file. Nothing in the repo is run, and the system's API is never called.

Accepts OpenAPI 3.x and Swagger 2.0, written in YAML or JSON. Limits keep a hostile file cheap:
- the file size is capped;
- YAML aliases are refused, so a small file can't expand into a huge one ("billion laughs");
- only local `$ref`s (`#/...`) are followed, with cycle and depth limits;
- the operation count and the size of each stored schema are capped.
Error messages are fixed text (safe to show to an admin and to put in events).
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .ingest import SKIP_DIRS

MAX_SPEC_BYTES = 2_000_000
MAX_OPERATIONS = 500
MAX_NESTING = 12            # schema nesting kept when inlining $refs
MAX_NODES = 5_000           # schema nodes kept per operation schema
MAX_SCHEMA_BYTES = 20_000   # bigger schemas are cut down to their top-level fields
MAX_LOAD_NODES = 500_000    # values in the whole file
FIND_DEPTH = 3
METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")
SPEC_NAMES = ("openapi.yaml", "openapi.yml", "openapi.json", "swagger.yaml", "swagger.yml", "swagger.json")
SPEC_SUFFIXES = (".yaml", ".yml", ".json")
SPEC_PATH = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


class SpecError(Exception):
    """A fixed, safe message about why the API file could not be read."""


class _NoAliasLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):  # type: ignore[override]
        if self.check_event(yaml.AliasEvent):
            raise SpecError("the API file uses YAML aliases (*name), which are not accepted")
        return super().compose_node(parent, index)


# ---------- finding the file ----------

def find_spec(root: Path, spec_path: str | None = None) -> Path:
    """The API file inside a checkout: `spec_path` if given, else the best-known name near the top."""
    root = root.resolve()
    if spec_path:
        return _given_path(root, spec_path)
    found: list[tuple[int, int, str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        depth = len(Path(dirpath).relative_to(root).parts)
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")) \
            if depth < FIND_DEPTH else []
        for fname in filenames:
            if fname.lower() in SPEC_NAMES:
                path = Path(dirpath, fname)
                if not path.is_symlink() and path.is_file():
                    found.append((depth, SPEC_NAMES.index(fname.lower()), path.as_posix(), path))
    if not found:
        raise SpecError("no OpenAPI file found (looked for openapi.yaml, openapi.json, swagger.yaml or "
                        "swagger.json in the top 3 folders); give the file's path")
    return min(found)[3]


def _given_path(root: Path, spec_path: str) -> Path:
    if not SPEC_PATH.match(spec_path):
        raise SpecError("the API file path may only use letters, numbers, . _ - and /")
    rel = PurePosixPath(spec_path)
    if rel.is_absolute() or ".." in rel.parts or rel.suffix.lower() not in SPEC_SUFFIXES:
        raise SpecError("the API file path must be a .yaml, .yml or .json file inside the repo")
    path = root.joinpath(*rel.parts)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise SpecError("the API file was not found at that path")
    return path


# ---------- loading ----------

def load_spec(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_SPEC_BYTES:
        raise SpecError(f"the API file is larger than {MAX_SPEC_BYTES // 1_000_000} MB")
    text = path.read_bytes().decode("utf-8", errors="replace")
    try:
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            data = yaml.load(text, Loader=_NoAliasLoader)  # noqa: S506 - SafeLoader subclass, aliases refused
    except SpecError:
        raise
    except (ValueError, yaml.YAMLError):
        raise SpecError("the API file is not valid YAML or JSON") from None
    except RecursionError:
        raise SpecError("the API file is nested too deeply") from None
    data = _plain(data, [0], 0)
    if not isinstance(data, dict):
        raise SpecError("the API file is not an OpenAPI document")
    openapi, swagger = data.get("openapi"), data.get("swagger")
    if not (isinstance(openapi, str) and openapi.startswith("3.")) and swagger != "2.0":
        raise SpecError("only OpenAPI 3.x and Swagger 2.0 files are supported")
    if not isinstance(data.get("paths"), dict):
        raise SpecError("the API file has no paths")
    return data


def _plain(value: Any, seen: list[int], depth: int) -> Any:
    """JSON-only values: string keys, dates as text. Bounded so a weird file can't blow up."""
    seen[0] += 1
    if seen[0] > MAX_LOAD_NODES or depth > 200:
        raise SpecError("the API file is too large or nested too deeply")
    if isinstance(value, dict):
        return {str(k): _plain(v, seen, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v, seen, depth + 1) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


# ---------- reading operations ----------

def info(spec: dict[str, Any]) -> tuple[str, str]:
    block = spec.get("info") if isinstance(spec.get("info"), dict) else {}
    return _text(block.get("title"), 100), _text(block.get("version"), 50)


def read_operations(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """One entry per path + method: name, method, path, summary, input_schema, output_schema."""
    v2 = spec.get("swagger") == "2.0"
    used: set[str] = set()
    out: list[dict[str, Any]] = []
    for path, item in spec["paths"].items():
        if not isinstance(item, dict):
            continue
        item = _deref(spec, item)
        shared = item.get("parameters") if isinstance(item.get("parameters"), list) else []
        for method in METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            if len(out) >= MAX_OPERATIONS:
                raise SpecError(f"the API file lists more than {MAX_OPERATIONS} operations")
            params = shared + (op.get("parameters") if isinstance(op.get("parameters"), list) else [])
            out.append({
                "name": _name(op.get("operationId"), method, path, used),
                "method": method.upper(),
                "path": str(path)[:300],
                "summary": _text(op.get("summary") or op.get("description"), 500) or f"{method.upper()} {path}"[:500],
                "input_schema": _fit(_inputs(spec, params, op, v2)),
                "output_schema": _fit(_output(spec, op, v2)),
            })
    return out


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value).split())[:limit] if isinstance(value, (str, int, float)) else ""


def _name(operation_id: Any, method: str, path: str, used: set[str]) -> str:
    raw = operation_id if isinstance(operation_id, str) and operation_id.strip() else f"{method}_{path}"
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw)
    snake = re.sub(r"[^a-z0-9]+", "_", snake.lower()).strip("_") or method
    if not snake[0].isalpha():
        snake = f"op_{snake}"
    base = snake[:64].rstrip("_")
    name, n = base, 2
    while name in used:
        suffix = f"_{n}"
        name = base[:64 - len(suffix)] + suffix
        n += 1
    used.add(name)
    return name


def _pointer(spec: dict[str, Any], ref: str) -> Any:
    node: Any = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return None
    return node


def _deref(spec: dict[str, Any], node: Any, hops: int = 0) -> Any:
    """Follow a chain of $refs on one object (parameters, responses, path items)."""
    while isinstance(node, dict) and isinstance(node.get("$ref"), str) and hops < 10:
        ref = node["$ref"]
        node = _pointer(spec, ref) if ref.startswith("#/") else None
        hops += 1
    return node if isinstance(node, dict) else {}


class _Inliner:
    """Copies a schema with local $refs inlined, within node and nesting limits."""

    def __init__(self, spec: dict[str, Any]):
        self.spec = spec
        self.left = MAX_NODES

    def __call__(self, node: Any, depth: int = 0, stack: frozenset[str] = frozenset()) -> Any:
        self.left -= 1
        if self.left < 0 or depth > MAX_NESTING:
            return {}
        if isinstance(node, list):
            return [self(v, depth + 1, stack) for v in node]
        if not isinstance(node, dict):
            return node
        ref = node.get("$ref")
        if isinstance(ref, str):
            if not ref.startswith("#/") or ref in stack:
                return {}
            return self(_pointer(self.spec, ref), depth + 1, stack | {ref})
        out = {k: self(v, depth + 1, stack) for k, v in node.items()}
        if isinstance(out.get("allOf"), list):
            out = _merge_all_of(out)
        return out


def _merge_all_of(schema: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {k: v for k, v in schema.items() if k != "allOf"}
    props = dict(merged.get("properties") or {})
    required = list(merged.get("required") or [])
    for part in schema["allOf"]:
        if isinstance(part, dict):
            props.update(part.get("properties") or {})
            required += [r for r in part.get("required") or [] if isinstance(r, str)]
    merged.setdefault("type", "object")
    merged["properties"] = props
    if required:
        merged["required"] = sorted(set(required))
    return merged


def _param_schema(param: dict[str, Any], v2: bool) -> Any:
    if not v2 and isinstance(param.get("schema"), dict):
        return param["schema"]
    return {k: param[k] for k in ("type", "format", "items", "enum", "pattern", "maxLength", "minimum", "maximum")
            if k in param}


def _inputs(spec: dict[str, Any], params: list[Any], op: dict[str, Any], v2: bool) -> dict[str, Any]:
    inline = _Inliner(spec)
    props: dict[str, Any] = {}
    required: list[str] = []
    body: Any = None
    for raw in params:
        param = _deref(spec, raw)
        name, where = param.get("name"), param.get("in")
        if not isinstance(name, str) or not name:
            continue
        if where == "body" and v2:
            body = param.get("schema")
            continue
        if where not in ("path", "query", "formData"):
            continue
        props[name] = inline(_param_schema(param, v2))
        if isinstance(props[name], dict) and isinstance(param.get("description"), str):
            props[name].setdefault("description", _text(param["description"], 300))
        if param.get("required") or where == "path":
            required.append(name)
    if not v2:
        request = _deref(spec, op.get("requestBody"))
        body = _content_schema(request.get("content"))
    if body is not None:
        body = inline(body)
        if isinstance(body, dict) and isinstance(body.get("properties"), dict):
            for name, spec_ in body["properties"].items():
                props.setdefault(name, spec_)
            required += [r for r in body.get("required") or [] if isinstance(r, str) and r in props]
        else:
            props.setdefault("body", body if isinstance(body, dict) else {})
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = sorted(set(required))
    return schema


def _content_schema(content: Any) -> Any:
    if not isinstance(content, dict) or not content:
        return None
    for media in ("application/json", *content):
        entry = content.get(media)
        if isinstance(entry, dict) and isinstance(entry.get("schema"), dict):
            return entry["schema"]
    return None


def _output(spec: dict[str, Any], op: dict[str, Any], v2: bool) -> dict[str, Any]:
    responses = op.get("responses") if isinstance(op.get("responses"), dict) else {}
    codes = [c for c in ("200", "201", "202", "2XX", "2xx") if c in responses]
    codes += sorted(c for c in responses if c.startswith("2") and c not in codes)
    codes += ["default"] if "default" in responses else []
    for code in codes:
        response = _deref(spec, responses[code])
        schema = response.get("schema") if v2 else _content_schema(response.get("content"))
        if isinstance(schema, dict):
            out = _Inliner(spec)(schema)
            return out if isinstance(out, dict) else {}
    return {}


def _fit(schema: dict[str, Any]) -> dict[str, Any]:
    """Keep stored schemas small: past the cap, keep only the top-level field names and types."""
    if len(json.dumps(schema)) <= MAX_SCHEMA_BYTES:
        return schema
    target = schema.get("items") if schema.get("type") == "array" and isinstance(schema.get("items"), dict) else schema
    props = target.get("properties") if isinstance(target.get("properties"), dict) else {}
    slim = {name: ({"type": spec["type"]} if isinstance(spec, dict) and isinstance(spec.get("type"), (str, list)) else {})
            for name, spec in list(props.items())[:200]}
    top = {"type": "object", "properties": slim, "x-replic8-trimmed": True}
    return {"type": "array", "items": top} if target is not schema else top
