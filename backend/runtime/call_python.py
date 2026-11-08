"""REPLIC8 Python caller. Runs inside the sandbox container only.

Usage: call_python.py /app/<file>.py FUNCTION
Reads one JSON object from stdin, calls FUNCTION from that file with the object as keyword
arguments, and prints the result as one JSON object. This file is fixed; nothing in it comes
from the model or the repo.

Exit codes (the same meanings as the line-protocol shim): 0 ok, 1 bad input, 2 the legacy code
failed, 3 no such function.

What the legacy code can and cannot do while it runs:
- Whatever it prints, including raw writes to file descriptor 1, goes to /dev/null. Only the
  answer below is written to the real stdout, through a copy of the descriptor made first.
- Its stdin is empty, so code that waits for input fails instead of hanging.
- Errors are reported by type only. The message may contain data, so it is never passed on.
"""

import datetime
import decimal
import importlib.util
import inspect
import json
import os
import re
import sys

MAX_INPUT = 64_000


def fail(message, code=1):
    sys.stderr.write(message + "\n")
    sys.exit(code)


def encode(value):
    """JSON for the values old code tends to return that json cannot handle itself."""
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def main():
    if len(sys.argv) != 3:
        fail("usage: call_python.py FILE FUNCTION")
    path, name = sys.argv[1], sys.argv[2]
    if not re.fullmatch(r"/app/[A-Za-z0-9_][A-Za-z0-9_./-]*\.py", path) or ".." in path.split("/"):
        fail("bad file")
    real = os.path.realpath(path)
    if not real.startswith("/app/") or not os.path.isfile(real):
        fail("no such file", 3)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
        fail("bad function name")

    raw = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        fail("input too large")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        fail("input is not JSON")
    if not isinstance(payload, dict):
        fail("input must be a JSON object")

    answer = os.fdopen(os.dup(1), "w")  # our own copy of stdout, kept for the answer
    os.dup2(os.open(os.devnull, os.O_WRONLY), 1)
    os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
    sys.stdout = open(os.devnull, "w")
    sys.stdin = open(os.devnull)
    sys.dont_write_bytecode = True  # /app is read-only
    sys.path[:0] = [os.path.dirname(real), "/app"]

    spec = importlib.util.spec_from_file_location("replic8_legacy_" + re.sub(r"\W", "_", os.path.basename(real)[:-3]), real)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException as exc:  # an import error, a sys.exit(), anything the module does at load time
        fail(f"legacy error: import failed ({type(exc).__name__})", 2)

    func = getattr(module, name, None)
    if not callable(func) or inspect.isclass(func):
        fail("no such function", 3)
    try:
        inspect.signature(func).bind(**payload)
    except TypeError as exc:
        fail(f"bad input: {str(exc)[:120]}")
    except ValueError:
        pass  # no signature available; the call itself will say

    try:
        result = func(**payload)
    except BaseException as exc:
        fail(f"legacy error: {type(exc).__name__}", 2)

    body = result if isinstance(result, dict) else {"items": list(result)} if isinstance(result, (list, tuple)) else {"result": result}
    try:
        text = json.dumps(body, default=encode, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        fail("legacy error: the result is not JSON", 2)
    answer.write(text)
    answer.flush()
    sys.exit(0)


main()
