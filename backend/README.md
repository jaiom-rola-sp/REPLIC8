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
| `REPLIC8_SANDBOX_IMAGES` | Docker images the sandbox may run. Pin by digest. |
| `REPLIC8_NOTIFY_NUMBERS` | E.164 numbers that get status texts |

Never commit these values.
