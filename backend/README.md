# replic8 backend

Python + FastAPI. See [docs/prd.md](../docs/prd.md) for the plan and [docs/security.md](../docs/security.md) for the trust model.

## Modules

| Module | Job | Reqs |
|--------|-----|------|
| `config.py` | Settings from env vars; validates tokens, write allowlist, phone numbers | NFR Security |
| `models.py` | Operation, source location, contract test result, wrapper version | FR-2, FR-3, FR-11, FR-13 |
| `ingest.py` | Safe GitHub clone, language detection | FR-1, FR-11 |
| `guard.py` | Checks model proposals against real symbols and files | FR-2, FR-11, FR-13 |
| `sandbox.py` | Runs legacy code in a locked-down Docker container | FR-4 |
| `executor.py` | Calls an operation in the sandbox; checks input and output schemas | FR-3, FR-5 |
| `registry.py` | Versioned wrappers; publishes only tested operations; rollback | FR-3, FR-8 |
| `gateway.py` | One authenticated, read-only-by-default REST gateway | FR-5, FR-13 |
| `nemotron.py` | Nemotron client (OpenAI-compatible API): retries, timeouts, key safety | FR-2, FR-7 |
| `prompts.py` | Builds prompts: secret redaction, numbered files, injection fencing, source diffs | FR-2, FR-7 |
| `generate.py` | Proposes operations and repairs; repairs can't change an operation's contract | FR-2, FR-7 |
| `notify.py` | Send-only owner texts (Photon transport still to do) | FR-12 |

## Run the tests

```bash
cd backend
pip install -e ".[dev]"
docker pull alpine:3.20   # optional: enables the real sandbox tests
pytest -q
```

## Environment variables

| Variable | Meaning |
|----------|---------|
| `REPLIC8_DATA_DIR` | Where clones and the registry live (default `./data`, git-ignored) |
| `REPLIC8_GATEWAY_TOKENS` | Comma-separated bearer tokens, at least 32 characters each. Required. |
| `REPLIC8_WRITE_OPS` | Write tools to allow, e.g. `inventory.reserve_part`. Leave empty in v1. |
| `REPLIC8_SANDBOX_IMAGES` | Docker images the sandbox may run. Each must be pinned by digest (`name@sha256:...`) or startup fails. Images are never pulled at call time, so `docker pull` them first. |
| `REPLIC8_NOTIFY_NUMBERS` | E.164 numbers that get status texts |
| `NVIDIA_API_KEY` | Nemotron API key. Required for generation and healing. |
| `REPLIC8_NEMOTRON_MODEL` | Exact model id, currently `nvidia/nemotron-3.5-super-vl-120b-a12b`. Required. |
| `REPLIC8_NEMOTRON_BASE_URL` | Default `https://integrate.api.nvidia.com/v1` |
| `REPLIC8_NEMOTRON_STRUCTURED` | Default `1`: constrain output with `response_format` (NVIDIA rejects `nvext.guided_json`) |
| `REPLIC8_NEMOTRON_THINKING` | Default `0`. Thinking mode used ~3,700 tokens and cut answers off in testing |

Never commit these values.
