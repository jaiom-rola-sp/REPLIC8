"""Where legacy code comes from: GitHub (FR-1), or a local folder for the demo.

GitHub URLs go through ingest.clone (https://github.com/owner/repo only).

Local repos are for development and the demo, while the COBOL and Fortran
systems live in this monorepo. They are off unless REPLIC8_LOCAL_REPO_ROOT is
set, and only folders directly inside that root can be used: `local://<name>`.
Their "commit" is a SHA-1 over the files, so a code change gives a new version.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .ingest import (GIT_SAFE_FLAGS, SKIP_DIRS, Checkout, IngestError, _git_env, _scan, clone,
                     normalize_repo_url)

LOCAL = re.compile(r"^local://([a-z0-9][a-z0-9._-]{0,63})$")


class SourceError(IngestError):
    pass


def canonical_url(url: str, local_root: Path | None) -> str:
    match = LOCAL.match(url.strip()) if isinstance(url, str) else None
    if match:
        _local_dir(match.group(1), local_root)
        return f"local://local/{match.group(1)}"
    return normalize_repo_url(url)[2]


def _local_dir(name: str, local_root: Path | None) -> Path:
    if local_root is None:
        raise SourceError("local repos are disabled (set REPLIC8_LOCAL_REPO_ROOT)")
    root = local_root.resolve()
    path = (root / name).resolve()
    if path.parent != root or not path.is_dir() or path.is_symlink():
        raise SourceError("unknown local repo")
    return path


def _local_name(url: str) -> str | None:
    if url.startswith("local://local/"):
        return url.removeprefix("local://local/")
    match = LOCAL.match(url)
    return match.group(1) if match else None


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha1()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fname in sorted(filenames):
            path = Path(dirpath, fname)
            if path.is_symlink():
                continue
            rel = path.relative_to(root).as_posix()
            digest.update(rel.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def fetch(url: str, repos_root: Path, *, local_root: Path | None, max_bytes: int, max_files: int,
          timeout_s: float) -> Checkout:
    """Get the current code into repos_root/<repo key>/<commit>."""
    name = _local_name(url.strip())
    if name is None:
        return clone(url, repos_root, max_bytes=max_bytes, max_files=max_files, timeout_s=timeout_s)

    src = _local_dir(name, local_root)
    commit = _tree_hash(src)
    dest = repos_root / f"local__{name}" / commit
    if not dest.exists():
        repos_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=repos_root, prefix=".copy-") as tmp:
            work = Path(tmp) / "src"
            shutil.copytree(src, work, symlinks=True, ignore=shutil.ignore_patterns(*SKIP_DIRS))
            languages = _scan(work, max_bytes=max_bytes, max_files=max_files)
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(work, dest)
    else:
        languages = _scan(dest, max_bytes=max_bytes, max_files=max_files)
    return Checkout(owner="local", repo=name, url=f"local://local/{name}", commit=commit, path=dest,
                    languages=languages)


def latest_commit(url: str, *, local_root: Path | None, timeout_s: float = 30.0) -> str:
    """Cheap check for "has the legacy code changed?" without a full clone."""
    name = _local_name(url.strip())
    if name is not None:
        return _tree_hash(_local_dir(name, local_root))
    _, _, canonical = normalize_repo_url(url)
    with tempfile.TemporaryDirectory(prefix="replic8-lsremote-") as home:
        try:
            proc = subprocess.run(["git", *GIT_SAFE_FLAGS, "ls-remote", "--", canonical, "HEAD"],
                                  env=_git_env(home), capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise SourceError("checking the repo timed out") from exc
    sha = proc.stdout.split("\t", 1)[0].strip()
    if proc.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise SourceError("could not read the repo's latest commit")
    return sha
