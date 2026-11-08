"""REPLIC8 call shim. Runs inside the sandbox container only.

Usage: shim.py BINARY COMMAND
Reads one JSON object from stdin, calls the compiled legacy program with the
"legacy line protocol", and prints the result as one JSON object.

Legacy line protocol (what the demo COBOL and Fortran programs speak):
  stdin:  COMMAND, then one KEY=VALUE line per input field, then END
  stdout: KEY=VALUE lines. BEGIN-ITEMS starts a list; a line "--" closes one item.
          ERROR=<code> means the call failed.
Exit codes: 0 ok, 1 bad input or crash, 2 legacy error, 3 no such command (function missing).
Keys go out upper-case with hyphens (part_id -> PART-ID) and come back lower-case
with underscores. Values that look like numbers come back as numbers.
"""

import json
import re
import subprocess
import sys

KEY = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
MAX_IN = 16_000
MAX_OUT = 500_000


def fail(message, code=1):
    sys.stderr.write(message + "\n")
    sys.exit(code)


def to_legacy(payload):
    lines = []
    for key, value in payload.items():
        if not KEY.match(key):
            fail("bad input key")
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            fail("input values must be strings or numbers")
        text = str(value)
        if len(text) > 64 or any(c in text for c in "=\r\n") or any(ord(c) < 32 for c in text):
            fail("bad input value")
        lines.append(f"{key.upper().replace('_', '-')}={text}")
    return lines


def convert(value):
    value = value.strip()
    if NUMBER.match(value):
        return float(value) if "." in value else int(value)
    return value


def from_legacy(text):
    result, items, current = {}, None, {}
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.strip() == "BEGIN-ITEMS":
            items = []
            continue
        if line.strip() == "--":
            if items is None:
                fail("item separator outside a list")
            items.append(current)
            current = {}
            continue
        if "=" not in line:
            fail("unexpected output line from legacy program")
        key, value = line.split("=", 1)
        key = key.strip().lower().replace("-", "_")
        if not KEY.match(key):
            fail("bad output key from legacy program")
        if key == "error":
            fail(f"legacy error: {value.strip()[:40]}", code=2)
        if items is not None and key not in ("count",):
            current[key] = convert(value)
        else:
            result[key] = convert(value)
    if items is not None:
        if current:
            items.append(current)
        result["items"] = items
    return result


def main():
    if len(sys.argv) != 3:
        fail("usage: shim.py BINARY COMMAND")
    binary, command = sys.argv[1], sys.argv[2]
    if not binary.startswith("/build/") or ".." in binary:
        fail("binary must be in /build")
    # Java programs are packaged as one jar; run them with a small, single-GC JVM
    # so they fit the sandbox's memory and process limits.
    run = [binary]
    if binary.endswith(".jar"):
        run = ["java", "-XX:+UseSerialGC", "-XX:-UsePerfData", "-XX:TieredStopAtLevel=1",
               "-Xmx64m", "-Xss512k", "-jar", binary]
    if not re.match(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$", command):
        fail("bad command")
    raw = sys.stdin.read(MAX_IN + 1)
    if len(raw) > MAX_IN:
        fail("input too large")
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        fail("input is not JSON")
    if not isinstance(payload, dict):
        fail("input must be a JSON object")

    stdin = "\n".join([command.upper(), *to_legacy(payload), "END", ""])
    try:
        proc = subprocess.run(run, input=stdin.encode(), capture_output=True, timeout=8)
    except subprocess.TimeoutExpired:
        fail("legacy program timed out")
    if len(proc.stdout) > MAX_OUT:
        fail("legacy output too large")
    text = proc.stdout.decode("ascii", "replace")
    if "ERROR=UNKNOWN-COMMAND" in text:
        fail("legacy program has no such command", code=3)  # FunctionMissing
    if proc.returncode != 0:
        fail(f"legacy program exited with {proc.returncode}")
    print(json.dumps(from_legacy(text), separators=(",", ":")))


if __name__ == "__main__":
    main()
