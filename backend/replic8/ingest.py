"""Clone a legacy repo safely and detect its languages (FR-1, FR-11).

Trust issues handled here:
- Only https://github.com/<owner>/<repo> URLs, so the clone can't be pointed at
  internal hosts, local files, or other protocols (SSRF).
- Git runs with hooks off, submodules off, symlinks checked out as plain files,
  no credential prompts, no system/global config, and a timeout.
- The checkout is size- and file-count-limited, and pinned to a full commit SHA.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import sys
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
REPO = re.compile(r"^[A-Za-z0-9._-]{1,100}$")

LANGUAGES = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".java": "java",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cs": "csharp", ".go": "go", ".rb": "ruby",
    ".php": "php", ".rs": "rust", ".kt": "kotlin", ".swift": "swift", ".scala": "scala",
    ".pl": "perl", ".pm": "perl", ".pp": "pascal", ".lpr": "pascal", ".sh": "bash", ".lua": "lua", ".r": "r",
    ".cbl": "cobol", ".cob": "cobol", ".cpy": "cobol", ".f": "fortran", ".f90": "fortran",
    ".for": "fortran", ".pas": "pascal", ".bas": "basic", ".vb": "vbnet", ".adb": "ada",
    ".rpg": "rpg", ".pli": "pli", ".asm": "assembly", ".sql": "sql",
}
SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "__pycache__", ".venv"}


class IngestError(Exception):
    pass


@dataclass
class Checkout:
    owner: str
    repo: str
    url: str
    commit: str
    path: Path
    languages: dict[str, int]


def normalize_repo_url(url: str) -> tuple[str, str, str]:
    """Return (owner, repo, canonical_url) or raise IngestError."""
    if not isinstance(url, str) or len(url) > 300:
        raise IngestError("repo URL must be a short string")
    parts = urlsplit(url.strip())
    if parts.scheme != "https":
        raise IngestError("repo URL must use https")
    if parts.hostname != "github.com" or parts.netloc.lower() != "github.com":
        raise IngestError("repo URL must be on github.com with no username or port")
    if parts.query or parts.fragment:
        raise IngestError("repo URL must not have a query or fragment")
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) != 2:
        raise IngestError("repo URL must look like https://github.com/owner/repo")
    owner, repo = segments
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not OWNER.match(owner) or not REPO.match(repo) or repo in {".", ".."}:
        raise IngestError("invalid owner or repo name")
    return owner, repo, f"https://github.com/{owner}/{repo}.git"


# Passed through to git. SYSTEMROOT: on Windows, without it git can't resolve github.com ("Could not
# resolve host"), because the network stack needs it. It names the Windows folder and is not a secret.
GIT_ENV_KEEP = {"PATH", "HTTPS_PROXY", "https_proxy", "SSL_CERT_FILE", "GIT_SSL_CAINFO", "NO_PROXY", "no_proxy",
                "SYSTEMROOT"}


def _git_env(home: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.upper() in GIT_ENV_KEEP}
    env.update(
        HOME=home,
        GIT_TERMINAL_PROMPT="0",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_ASKPASS="/bin/false",
        GIT_LFS_SKIP_SMUDGE="1",
    )
    return env


GIT_SAFE_FLAGS = [
    "-c", "protocol.allow=never",
    "-c", "protocol.https.allow=always",
    "-c", f"core.hooksPath={os.devnull}",
    "-c", "core.symlinks=false",
    "-c", "core.fsmonitor=false",
    "-c", "submodule.recurse=false",
    "-c", "http.followRedirects=false",
    "-c", "credential.helper=",
]


def _remove_tree(path: Path) -> None:
    """shutil.rmtree that also removes read-only files. On Windows git marks its object files read-only,
    and a plain rmtree fails on them with "Access is denied"."""
    def make_writable_and_retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=make_writable_and_retry)
    else:
        shutil.rmtree(path, onerror=make_writable_and_retry)


def clone(url: str, repos_root: Path, *, max_bytes: int, max_files: int, timeout_s: float) -> Checkout:
    owner, repo, canonical = normalize_repo_url(url)
    repos_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=repos_root, prefix=".clone-") as tmp:
        home = Path(tmp) / "home"
        home.mkdir()
        work = Path(tmp) / "src"
        cmd = [
            "git", *GIT_SAFE_FLAGS, "clone", "--depth", "1", "--single-branch", "--no-tags",
            "--no-recurse-submodules", "--", canonical, str(work),
        ]
        try:
            proc = subprocess.run(cmd, env=_git_env(str(home)), capture_output=True, timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise IngestError("clone timed out") from exc
        if proc.returncode != 0:
            raise IngestError("clone failed (repo missing, private, or unreachable)")

        commit = subprocess.run(
            ["git", "-C", str(work), "rev-parse", "HEAD"], env=_git_env(str(home)), capture_output=True, text=True
        ).stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise IngestError("could not read the cloned commit")

        _remove_tree(work / ".git")
        languages = _scan(work, max_bytes=max_bytes, max_files=max_files)

        dest = repos_root / f"{owner.lower()}__{repo.lower()}" / commit
        if dest.exists():
            _remove_tree(work)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(work, dest)
    return Checkout(owner=owner, repo=repo, url=canonical, commit=commit, path=dest, languages=languages)


def _scan(root: Path, *, max_bytes: int, max_files: int) -> dict[str, int]:
    total = 0
    files = 0
    counts: Counter[str] = Counter()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not Path(dirpath, d).is_symlink()]
        for fname in filenames:
            path = Path(dirpath, fname)
            if path.is_symlink():
                path.unlink()
                continue
            files += 1
            total += path.stat().st_size
            if files > max_files or total > max_bytes:
                raise IngestError("repo is larger than the allowed size")
            lang = LANGUAGES.get(path.suffix.lower())
            if lang:
                counts[lang] += 1
    return dict(counts.most_common())
