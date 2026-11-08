import sys

import pytest

from replic8.ingest import IngestError, _scan, normalize_repo_url


@pytest.mark.parametrize("url,expected", [
    ("https://github.com/acme/legacy", ("acme", "legacy", "https://github.com/acme/legacy.git")),
    ("https://github.com/acme/legacy.git", ("acme", "legacy", "https://github.com/acme/legacy.git")),
    ("https://github.com/acme/legacy/", ("acme", "legacy", "https://github.com/acme/legacy.git")),
])
def test_accepts_plain_github_urls(url, expected):
    assert normalize_repo_url(url) == expected


@pytest.mark.parametrize("url", [
    "http://github.com/acme/legacy",             # not https
    "git@github.com:acme/legacy.git",            # ssh
    "file:///etc",                               # local file
    "https://github.com.evil.com/acme/legacy",   # look-alike host
    "https://user:pw@github.com/acme/legacy",    # credentials in URL
    "https://github.com:8443/acme/legacy",       # port
    "https://169.254.169.254/latest/meta-data",  # cloud metadata (SSRF)
    "https://localhost/acme/legacy",
    "https://github.com/acme/legacy/tree/main",  # extra path
    "https://github.com/acme/..",
    "https://github.com/acme/legacy?x=1",
    "https://github.com/-acme/legacy",
    "ext::sh -c touch% /tmp/pwned",              # git remote helper
])
def test_rejects_unsafe_urls(url):
    with pytest.raises(IngestError):
        normalize_repo_url(url)


@pytest.mark.skipif(sys.platform == "win32", reason="creating symlinks on Windows needs admin rights")
def test_scan_drops_symlinks_and_enforces_limits(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n")
    (tmp_path / "LEGACY.CBL").write_text("IDENTIFICATION DIVISION.\n")
    (tmp_path / "escape.py").symlink_to("/etc/passwd")
    langs = _scan(tmp_path, max_bytes=10_000, max_files=10)
    assert langs == {"python": 1, "cobol": 1}
    assert not (tmp_path / "escape.py").exists()
    with pytest.raises(IngestError):
        _scan(tmp_path, max_bytes=5, max_files=10)
    with pytest.raises(IngestError):
        _scan(tmp_path, max_bytes=10_000, max_files=1)
