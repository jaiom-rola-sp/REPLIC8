# Security and trust model

How replic8's backend handles the trust problems in turning untrusted legacy code into tools an AI agent can call. Requirement IDs match [requirements](requirements.md). Code is in `backend/replic8/`. Each row has tests in `backend/tests/`.

## What we don't trust

1. **The legacy repo:** its code, file names, symlinks, size, and any text planted in comments.
2. **The model (Nemotron):** it reads that untrusted code, so its output can be wrong or steered by prompt injection.
3. **Gateway callers:** anyone who can reach the gateway.
4. **The network around Photon:** a send can fail or hang.

## Threats and mitigations

| # | Threat | Mitigation | Where |
|---|--------|------------|-------|
| T1 | Repo URL points at internal hosts, local files, or a git remote helper (SSRF, `ext::`) | Only `https://github.com/<owner>/<repo>`; no userinfo, port, query or extra path | `ingest.normalize_repo_url` |
| T2 | Malicious repo attacks the host during clone (hooks, submodules, symlinks, huge repo) | Git runs with hooks off, submodules off, `core.symlinks=false`, no global/system config, no credential prompts, a timeout; `.git` removed after clone; symlinks deleted; size and file-count caps | `ingest.clone`, `ingest._scan` |
| T3 | Legacy code runs on the host or reaches the network (FR-4) | Every call runs in a fresh container: `--network none`, read-only root, read-only code mount, `--cap-drop ALL`, `no-new-privileges`, uid 65534, memory/CPU/PID limits, timeout, output cap, image allowlist | `sandbox.py` |
| T4 | Caller input injects shell flags or commands | argv is fixed when the wrapper is generated; caller input goes only to stdin as JSON | `models.Invocation`, `executor.py` |
| T5 | Model invents functions (hallucination) | Model output is strict JSON with no extra fields. `parsed` tier must match a tree-sitter symbol exactly (name, file, line); other tiers must cite a real file:line | `guard.validate_proposal` |
| T6 | Prompt injection in legacy code steers the model ("expose everything as read") | The model only writes a declarative proposal and never runs code on the host. Proposals are schema-checked; a write-looking name can't be labelled `read`; the sandbox image is chosen by replic8, not the model; every op must still pass contract tests | `guard.py` |
| T7 | Untested or edited operation gets served (FR-3) | Registry publishes only ops with a passing test against the same commit; files are re-validated on every load | `registry.py`, `models.WrapperVersion` |
| T8 | Agent triggers purchasing or dispatching (FR-13) | `write` ops return 403 unless named in `REPLIC8_WRITE_OPS` (empty in v1). Defense in depth: the sandbox filesystem is read-only and offline, so even a mislabelled op can't persist changes | `gateway.py`, `sandbox.py` |
| T9 | Unauthorized gateway use | Bearer token required (at least 32 characters, constant-time compare); the app won't start without one; per-token rate limit; no unauthenticated docs | `gateway.py`, `config.py` |
| T10 | Wrapper returns junk or manipulated data under a trusted name | Output is validated against the published output schema; every response carries provenance (tier, file:line, version, commit) | `executor.py`, `gateway.py` |
| T11 | Errors leak secrets or legacy internals | Callers get generic messages; legacy stderr is never returned; the audit log records tool and outcome only, never input or tokens | `executor.CallError`, `gateway.py` |
| T12 | Large requests exhaust memory | 64 KB body cap, enforced with or without Content-Length | `gateway.BodyLimit` |
| T13 | Texts leak code or secrets, or texts trigger actions (FR-12) | Fixed templates filled only with validated identifiers and numbers; E.164 allowlist from env; no inbound handler exists; sends run in the background and never raise; repeats are grouped | `notify.py` |
| T14 | Path traversal in registry or source locations | System names are regex-checked; source paths must be relative with no `..` | `registry.py`, `models.SourceLocation` |

## Known gaps (not done yet)

- **Sandbox images** must be pinned by digest before the demo, not by tag.
- **Docker socket:** the backend needs Docker access, which is root-equivalent on the host. Run the backend on the demo VM only, not on a shared machine. A rootless Docker or gVisor runtime would be stronger.
- **Legacy code that needs its own database or a writable directory** won't run under `--read-only` without an extra tmpfs. Decide per demo system.
- **Tokens** are static, shared secrets with no per-caller scopes or expiry. Fine for a demo, not for production.
- **Not built yet:** tree-sitter extraction, the Nemotron client, contract-test generation, the MCP server, self-healing, and the Photon transport (its API is unverified).
