"""REPLIC8 command-line caller. Runs inside the sandbox container only.

Usage: call_cli.py SPEC
SPEC is JSON written by REPLIC8 when it published the operation (never by the model or the caller):
  {"exe": ["/build/orders"], "args": ["lookup", "--part={part_id}", "{qty}"], "output": "json"|"keyvalue"|"lines"}
A token that is exactly "{field}" or ends with "={field}" takes that field from the caller's JSON on stdin,
each value becoming its own argument (there is no shell, so nothing in a value can be interpreted as syntax).
A value is refused if it is not short printable text, or if it would stand alone and start with "-"
(it could be read as a flag). Everything is checked here again even though REPLIC8 checked it at publish time.

Exit codes: 0 ok, 1 bad spec or protocol, 2 the program failed, 3 program missing, 4 a caller value was refused.
"""

import json
import os
import re
import subprocess
import sys

MAX_INPUT = 64_000
MAX_OUTPUT = 1_000_000
MAX_VALUE = 256
LITERAL = re.compile(r"^[A-Za-z0-9_./:,@%+=-]{1,64}$")
SLOT = re.compile(r"^(?:(--?[A-Za-z0-9][A-Za-z0-9_-]{0,40}=))?\{([A-Za-z_][A-Za-z0-9_]{0,63})\}$")
EXE = re.compile(r"^(?:/build/[a-z0-9_-]{1,64}|/app/[A-Za-z0-9_][A-Za-z0-9_./-]{0,250}|perl|php|python3)$")
OUTPUTS = {"json", "keyvalue", "lines"}


def fail(message, code=1):
    sys.stderr.write(message + "\n")
    sys.exit(code)


def value_text(value, standalone):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        fail("bad input: values must be text or numbers", 4)
    text = value if isinstance(value, str) else json.dumps(value)
    if not text or len(text) > MAX_VALUE or any(ord(c) < 32 or ord(c) == 127 for c in text):
        fail("bad input: a value is empty, too long or not printable", 4)
    if standalone and text.startswith("-"):
        fail("bad input: a value may not start with '-'", 4)
    return text


def number_or_text(text):
    if re.fullmatch(r"-?\d{1,15}", text):
        return int(text)
    if re.fullmatch(r"-?\d{1,15}\.\d{1,15}", text):
        return float(text)
    return text


def parse(output, stdout):
    if output == "json":
        try:
            body = json.loads(stdout)
        except ValueError:
            fail("legacy error: output is not JSON", 2)
        return body if isinstance(body, dict) else {"items": body} if isinstance(body, list) else {"result": body}
    lines = [ln.rstrip() for ln in stdout.splitlines() if ln.strip()]
    if output == "lines":
        return {"lines": lines[:1000]}
    found = {}
    for ln in lines:
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_ .-]{0,63}?)\s*[=:]\s*(.*)$", ln)
        if m and len(found) < 200:
            found.setdefault(re.sub(r"[^a-z0-9]+", "_", m.group(1).lower()).strip("_"), number_or_text(m.group(2).strip()))
    if not found:
        fail("legacy error: no key/value lines in the output", 2)
    return found


def main():
    if len(sys.argv) != 2 or len(sys.argv[1]) > 4096:
        fail("usage: call_cli.py SPEC")
    try:
        spec = json.loads(sys.argv[1])
        exe, args, output = spec["exe"], spec["args"], spec["output"]
    except (ValueError, KeyError, TypeError):
        fail("bad spec")
    if (not isinstance(exe, list) or not 1 <= len(exe) <= 2 or not all(isinstance(x, str) and EXE.match(x) for x in exe)
            or ".." in " ".join(exe).split("/") or not isinstance(args, list) or len(args) > 20
            or not all(isinstance(a, str) for a in args) or output not in OUTPUTS):
        fail("bad spec")

    raw = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        fail("input too large")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        fail("input is not JSON")
    if not isinstance(payload, dict):
        fail("input must be a JSON object")

    argv = list(exe)
    for token in args:
        slot = SLOT.match(token)
        if slot:
            prefix, field = slot.groups()
            if field not in payload:
                continue  # an optional field the caller left out
            argv.append((prefix or "") + value_text(payload[field], standalone=not prefix))
        elif LITERAL.match(token):
            argv.append(token)
        else:
            fail("bad spec")
    if any(x.startswith(("/build/", "/app/")) and not os.path.exists(x) for x in exe):
        fail("no such program", 3)

    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "HOME": "/tmp"}
    try:
        done = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              env=env, cwd="/tmp", timeout=20)
    except subprocess.TimeoutExpired:
        fail("legacy error: timed out", 2)
    except OSError:
        fail("no such program", 3)
    if done.returncode != 0:
        fail(f"legacy error: exit status {done.returncode}", 2)
    if len(done.stdout) > MAX_OUTPUT:
        fail("legacy error: output too large", 2)
    body = parse(output, done.stdout.decode("utf-8", "replace"))
    try:
        sys.stdout.write(json.dumps(body, separators=(",", ":"), allow_nan=False))
    except (TypeError, ValueError):
        fail("legacy error: the result is not JSON", 2)
    sys.exit(0)


main()
