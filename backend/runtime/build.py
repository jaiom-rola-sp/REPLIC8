"""REPLIC8 build step. Runs inside the sandbox container only, with no network.

Compiles every COBOL and Fortran source under /app (read-only) into /build/<name>,
and all Java sources together into /build/app.jar (main class found from the code).
The commands are fixed here; nothing comes from the model or the repo.
"""

import os
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

print(f"built={len(built)} failed={len(failed)}")
sys.exit(0 if built and not failed else 1)
