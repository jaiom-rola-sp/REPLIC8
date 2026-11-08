"""REPLIC8 build step. Runs inside the sandbox container only, with no network.

Compiles every COBOL and Fortran source under /app (read-only) into /build/<name>,
all Java sources together into /build/app.jar (main class found from the code),
C into /build/<main file name> (all .c files together when exactly one has main(), otherwise each program alone),
and each Pascal program into /build/<name>. Python, Perl and PHP are not compiled: each file gets a
syntax check only, so a broken script fails the build here instead of at the first call.
The commands are fixed here; nothing comes from the model or the repo.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

COMPILERS = {
    ".cbl": ["cobc", "-x", "-O"],
    ".cob": ["cobc", "-x", "-O"],
    ".f90": ["gfortran", "-O1", "-std=legacy"],
    ".f": ["gfortran", "-O1", "-std=legacy"],
    ".for": ["gfortran", "-O1", "-std=legacy"],
}

out = Path("/build")
built, failed = [], []


def build_java(sources):
    """Compile all .java files into one jar. Exactly one class may have a main method."""
    mains = []
    for src in sources:
        text = src.read_text(errors="replace")
        if "static void main(" in text:
            pkg = next((l.split()[1].rstrip(";") for l in text.splitlines() if l.strip().startswith("package ")), "")
            mains.append(f"{pkg}.{src.stem}" if pkg else src.stem)
    if len(mains) != 1:
        sys.stderr.write(f"java: expected one main class, found {len(mains)}\n")
        return False
    classes = Path("/tmp/classes")
    classes.mkdir(exist_ok=True)
    proc = subprocess.run(["javac", "-nowarn", "-encoding", "ISO-8859-1", "-d", str(classes),
                           *[str(s) for s in sources]], capture_output=True, timeout=120)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-2000:])
        return False
    proc = subprocess.run(["jar", "--create", "--file", str(out / "app.jar"), "--main-class", mains[0],
                           "-C", str(classes), "."], capture_output=True, timeout=60)
    sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-500:])
    return proc.returncode == 0


java = sorted(p for p in Path("/app").rglob("*.java") if p.is_file() and not p.is_symlink())
if java:
    (built if build_java(java) else failed).append(f"{len(java)} java file(s)")

for path in sorted(Path("/app").rglob("*")):
    if path.is_symlink() or not path.is_file():
        continue
    compiler = COMPILERS.get(path.suffix.lower())
    if compiler is None:
        continue
    target = out / path.stem.lower()
    proc = subprocess.run([*compiler, "-o", str(target), str(path)], capture_output=True, timeout=90,
                          env={**os.environ, "TMPDIR": "/tmp"})
    if proc.returncode == 0:
        built.append(path.relative_to("/app").as_posix())
    else:
        failed.append(path.relative_to("/app").as_posix())
        sys.stderr.write(proc.stderr.decode("utf-8", "replace")[-2000:])


SKIP_DIRS = {".git", "node_modules", "vendor", "__pycache__", ".venv"}


def files(*suffixes):
    return sorted(p for p in Path("/app").rglob("*")
                  if p.is_file() and not p.is_symlink() and p.suffix.lower() in suffixes
                  and not (set(p.relative_to("/app").parts[:-1]) & SKIP_DIRS))


def rel(path):
    return path.relative_to("/app").as_posix()


def run(cmd, timeout=90):
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, env={**os.environ, "TMPDIR": "/tmp"})
    except subprocess.TimeoutExpired:
        sys.stderr.write(f"timed out: {cmd[0]}\n")
        return False
    if proc.returncode != 0:  # fpc reports errors on stdout, the others on stderr
        sys.stderr.write((proc.stdout[-1000:] + proc.stderr[-1500:]).decode("utf-8", "replace"))
    return proc.returncode == 0


def record(label, ok):
    (built if ok else failed).append(label)


def text(path):
    return path.read_text(errors="replace")


c_files = files(".c")
if c_files:
    includes = [f"-I{d}" for d in sorted({str(p.parent) for p in files(".h")})[:20]]
    mains = [p for p in c_files if re.search(r"\bmain\s*\(", text(p))]
    if len(mains) == 1:
        record(f"{len(c_files)} c file(s)", run(["gcc", "-O1", "-w", *includes, "-o", str(out / mains[0].stem.lower()), *map(str, c_files), "-lm"], 120))
    elif mains:
        for p in mains:
            record(rel(p), run(["gcc", "-O1", "-w", *includes, "-o", str(out / p.stem.lower()), str(p), "-lm"]))
    else:
        sys.stderr.write("c: no file has a main() function\n")
        record("c: no main()", False)

pascal = files(".pas", ".pp", ".lpr")
if pascal:
    units = [f"-Fu{d}" for d in sorted({str(p.parent) for p in pascal})[:20]]
    programs = [p for p in pascal if re.search(r"^\s*program\s+\w+", text(p), re.I | re.M)]
    Path("/tmp/fpc").mkdir(exist_ok=True)
    for p in programs:
        record(rel(p), run(["fpc", "-O1", *units, "-FU/tmp/fpc", f"-o{out / p.stem.lower()}", str(p)]))
    if not programs:
        sys.stderr.write("pascal: no file starts with a program statement\n")
        record("pascal: no program", False)

for p in files(".py"):
    record(rel(p), run(["python3", "-c", "import ast, sys; ast.parse(open(sys.argv[1], 'rb').read())", str(p)], 30))
for p in files(".pl", ".pm"):
    record(rel(p), run(["perl", "-c", f"-I{p.parent}", "-I/app", str(p)], 30))
for p in files(".php"):
    record(rel(p), run(["php", "-l", str(p)], 30))

sys.stderr.write(f"built={len(built)} failed={len(failed)}\n")
if not built or failed:
    sys.exit(1)

# Send the results back: a tar stream of the files in /build on stdout (the only thing on stdout).
# The backend unpacks it; the container never writes to the host.
import tarfile  # noqa: E402

sys.stdout.flush()
with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tar:
    for path in sorted(out.iterdir()):
        if path.is_file() and not path.is_symlink():
            tar.add(str(path), arcname=path.name, recursive=False)
sys.exit(0)
