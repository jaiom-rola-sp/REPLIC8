# Security and trust model

How REPLIC8's backend handles the trust problems in turning untrusted legacy code into tools an AI agent can call. Requirement IDs match [requirements](requirements.md). Code is in `backend/replic8/`. Each row has tests in `backend/tests/`.

## What we don't trust

1. **The legacy repo:** its code, file names, symlinks, size, and any text planted in comments.
2. **The model (Nemotron):** it reads that untrusted code, so its output can be wrong or steered by prompt injection.
3. **Gateway callers:** anyone who can reach the gateway.

## Threats and mitigations

| # | Threat | Mitigation | Where |
|---|--------|------------|-------|
| T1 | Repo URL points at internal hosts, local files, or a git remote helper (SSRF, `ext::`) | Only `https://github.com/<owner>/<repo>`; no userinfo, port, query or extra path | `ingest.normalize_repo_url` |
| T2 | Malicious repo attacks the host during clone (hooks, submodules, symlinks, huge repo) | Git runs with hooks off, submodules off, `core.symlinks=false`, no global/system config, no credential prompts, a timeout; `.git` removed after clone; symlinks deleted; size and file-count caps | `ingest.clone`, `ingest._scan` |
| T3 | Legacy code runs on the host or reaches the network (FR-4) | Every call runs in a fresh container: `--network none`, read-only root, read-only code mount, `--cap-drop ALL`, `no-new-privileges`, uid 65534, memory/CPU/PID limits, timeout, output cap, image allowlist | `sandbox.py` |
| T4 | Caller input injects shell flags or commands | argv is fixed when the wrapper is generated; caller input goes only to stdin as JSON | `models.Invocation`, `executor.py` |
| T5 | Model invents functions (hallucination) | Model output is strict JSON with no extra fields. `parsed` tier must match a tree-sitter symbol exactly (name, file, line); other tiers must cite a real file:line | `guard.validate_proposal` |
| T6 | Prompt injection in legacy code steers the model ("expose everything as read") | The model only writes a declarative proposal and never runs code on the host. Proposals are schema-checked; a write-looking name can't be labelled `read`; the sandbox image is chosen by REPLIC8, not the model; every op must still pass contract tests | `guard.py` |
| T7 | Untested or edited operation gets served (FR-3) | Registry publishes only ops with a passing test against the same commit; files are re-validated on every load | `registry.py`, `models.WrapperVersion` |
| T8 | Agent triggers purchasing or dispatching (FR-13) | `write` ops return 403 unless named in `REPLIC8_WRITE_OPS` (empty in v1). Defense in depth: the sandbox filesystem is read-only and offline, so even a mislabelled op can't persist changes | `gateway.py`, `sandbox.py` |
| T9 | Unauthorized gateway use | Bearer token required (at least 32 characters, constant-time compare); the app won't start without one; per-token rate limit; per-token scopes from `REPLIC8_TOKEN_SCOPES` (`ns.*` or one tool), with 403 outside them and no access for a token without scopes (fail closed); listing shows only in-scope tools; no unauthenticated docs. Every route goes through `validate_call` | `validator.py`, `gateway.py`, `config.py` |
| T10 | Wrapper returns junk or manipulated data under a trusted name | Output is validated against the published output schema; every response carries provenance (tier, file:line, version, commit) | `executor.py`, `gateway.py` |
| T11 | Errors leak secrets or legacy internals | Callers get generic messages; legacy stderr is never returned; the audit log records tool and outcome only, never input or tokens | `executor.CallError`, `gateway.py` |
| T12 | Large requests exhaust memory | 64 KB body cap, enforced with or without Content-Length | `gateway.BodyLimit` |
| T13 | ~~Texts leak code or secrets, or texts trigger actions (FR-12)~~ | Dropped with Photon (2026-11-08). No messaging code exists, so there is no outbound or inbound text path. | n/a |
| T14 | Path traversal in registry or source locations | System names are regex-checked; source paths must be relative with no `..` | `registry.py`, `models.SourceLocation` |
| T15 | Secrets in legacy code get sent to NVIDIA's API | Keys, passwords, tokens, private keys and credentials in URLs are replaced with `<redacted>` before sending (line numbers kept). Vendored folders are skipped and context is size-capped | `prompts.redact`, `prompts.build_context` |
| T16 | Prompt injection through code comments or the diff | Code and diffs are wrapped in markers with a random nonce, and the model is told their contents are data. This only lowers the risk; T5 and T6 are the real gate | `prompts.py` |
| T17 | A self-heal silently changes what agents get | A repair must keep each operation's name and input/output schemas, can't add operations, and can't relabel a write as read. Anything else is rejected as a breaking change for a human | `generate.heal` |
| T18 | Model writes code or a shell command that then runs | The model's answer has no command field at all (extra fields are rejected). REPLIC8 builds each command from the language, file and function, and refuses any that starts a shell. Seen in live testing: the model tried inline `python3 -c` code | `guard.py`, `guard.SHELLS` |
| T20 | Compiling legacy code attacks the host | The build runs in the sandbox too: no network, read-only code, only the build output folder writable, fixed compiler commands from REPLIC8 | `sandbox.Sandbox.build`, `runtime/build.py` |
| T21 | Caller input smuggles an extra command into the legacy program | The shim allows only short printable values with no `=` or newlines, and keys matching a strict pattern | `runtime/shim.py` |
| T22 | Parser confusion on old dialects invents a function | When a grammar only partly parses a file, each symbol is kept only if its name is really on its reported line; the file is reported as partly parsed | `extract._confirmed` |
| T23 | An agent token is used to onboard repos, trigger repairs or roll back | Admin routes need a separate admin token (must differ from gateway tokens); the admin API is off when none is set | `validator.Validator`, `gateway.py` |
| T24 | A website tricks a browser into calling the local MCP endpoint (DNS rebinding) | MCP checks the Host header against `REPLIC8_ALLOWED_HOSTS` (localhost by default) and still needs a bearer token | `gateway.py`, `mcp_server.McpAuth` |
| T25 | A legacy repo change silently changes live answers | Published versions are pinned to the tested commit. New code is retested first; only identical replays are saved | `pipeline._heal`, `contracts.replay_contract` |
| T26 | The model guesses an output schema that hides or misdescribes real data | Output schemas are learned from real recorded outputs; the model's guess is discarded | `contracts.observed_schema` |
| T27 | A local demo repo path escapes its folder | Off by default; only `local://<name>` for folders directly inside `REPLIC8_LOCAL_REPO_ROOT`; symlinks skipped | `sources.py` |
| T28 | The activity log leaks code, inputs or secrets, or carries script into the dashboard | Events take only identifiers, versions, counts and fixed kinds; text is stripped to a safe character set | `events.py` |
| T29 | A browser on another site calls the gateway | No CORS unless exact origins are listed; `*` is refused | `config.py`, `gateway.py` |
| T30 | A hostile legacy file hangs the parser and freezes onboarding | Each file is parsed in a child process with a 10-second limit; a file that times out is reported as partly parsed and gets no symbols. (Found while testing: the COBOL grammar never finishes on a file containing just `x`.) | `extract._parse_isolated` |
| T31 | The hosted backend is exposed or over-privileged | Only Caddy (80/443) is public; the app listens on localhost; it runs as a non-root service user with systemd hardening and one writable folder; secrets live in a 0640 env file; grammars are fetched at setup, not at runtime | `deploy/vm/` |
| T19 | API key leaks or goes to the wrong host | Key only from `NVIDIA_API_KEY` (in the cloud session, injected by the network proxy so code never sees it); https-only base URL; redirects not followed; key kept out of logs, errors and `repr` | `nemotron.py` |

## Known gaps (not done yet)

- ~~**Sandbox images** must be pinned by digest before the demo, not by tag.~~ **Done 2026-11-07:** startup refuses images not pinned by digest, and `docker run --pull never` stops downloads at call time.
- **Docker socket:** the backend needs Docker access, which is root-equivalent on the host. Run the backend on the demo VM only, not on a shared machine. A rootless Docker or gVisor runtime would be stronger.
- **Legacy code that needs its own database or a writable directory** won't run under `--read-only` without an extra tmpfs. Decide per demo system.
- **Tokens** are static, shared secrets with no expiry or rotation (per-token scopes now exist, see T9). Fine for a demo, not for production.
- **Redaction is pattern-based.** It catches common secret shapes, not all of them. Don't ingest repos with real customer data or live credentials.
- **Model-written input schemas can be wrong.** In live testing the model once wrote a `request_id` pattern that rejected the real ID `R-1001`. Operator-supplied examples catch this; without them, a too-strict schema just fails its contract test.
- **Contract tests prove consistency, not correctness.** A repair must reproduce recorded answers, but the first recording is only as good as its example inputs. Give real example IDs when onboarding.
- **Background jobs are in-process.** Onboarding and repairs run in threads of the gateway process; a restart mid-job drops the job (the registry stays consistent).
- **Not built yet:** the `inferred` and `black-box` tiers, and token expiry or rotation. (Per-token scopes exist, see T9. Photon texts were dropped, so T13 no longer applies.)
