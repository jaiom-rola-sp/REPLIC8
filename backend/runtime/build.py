"""REPLIC8 build step. Runs inside the sandbox container only, with no network.

Compiles every COBOL and Fortran source under /app (read-only) into /build/<name>.
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
