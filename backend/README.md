# REPLIC8 backend

Python + FastAPI. See [docs/prd.md](../docs/prd.md) for the plan and [docs/security.md](../docs/security.md) for the trust model.

**MCP is the main interface.** Agents connect to `/mcp` and get one tool per published legacy operation (`maintenance.get_request`, `inventory.check_stock`, ...), marked read-only, with source and version in every result. The same tools are also served as a REST API with OpenAPI, through the same security checks.

## Connect an MCP client

The endpoint is `http://127.0.0.1:8000/mcp` (Streamable HTTP) with a gateway token as a bearer token.

- **Claude Code:**

```bash
claude mcp add --transport http replic8 http://127.0.0.1:8000/mcp --header "Authorization: Bearer <gateway token>"
```

- **Any client:** point it at the URL above and send `Authorization: Bearer <gateway token>`.
- **Demo script:** `REPLIC8_TOKEN=<gateway token> python scripts/mcp_demo.py` connects like an agent at Company A, lists the tools, and chains B's pump request to C's stock and shipping options.

## Modules

| Module | Job | Reqs |
|--------|-----|------|
| `config.py` | Settings from env vars; validates tokens, write allowlist, origins and hosts | NFR Security |
| `models.py` | Operation, source location, contract test result, wrapper version | FR-2, FR-3, FR-11, FR-13 |
| `ingest.py` | Safe GitHub clone, language detection | FR-1, FR-11 |
| `guard.py` | Checks model proposals against real symbols and files | FR-2, FR-11, FR-13 |
| `sandbox.py` | Runs legacy code in a locked-down Docker container | FR-4 |
| `executor.py` | Calls an operation in the sandbox; checks input and output schemas | FR-3, FR-5 |
| `registry.py` | Versioned wrappers; publishes only tested operations; rollback | FR-3, FR-8 |
| `gateway.py` | One authenticated, read-only-by-default gateway: REST, MCP, OpenAPI, graph, events, admin | FR-2, FR-5, FR-6, FR-8, FR-13 |
| `validator.py` | `Validator.validate_call` (PRD section 7): token checks, per-token scopes, admin tokens, rate limit, audit log; used by REST and MCP | FR-5, FR-13 |
| `mcp_server.py` | **The main interface:** MCP tools over Streamable HTTP at `/mcp`, through the same checks as REST | FR-2, FR-5 |
| `contracts.py` | Contract tests: record real input/output cases; replay them after a repair | FR-3, FR-7 |
| `pipeline.py` | Onboarding and self-heal; `trigger_heal` (PRD section 7); change polling; rollback | FR-1 to FR-8 |
| `sources.py` | GitHub or local demo repos; latest-commit checks | FR-1, FR-7 |
| `graph.py` | Graph nodes and data edges from real field names | FR-6 |
| `events.py` | Sanitized activity log for the dashboard | FR-6, FR-7 |
| `main.py` | Builds everything from env vars; `python -m replic8` starts the server | |
| `nemotron.py` | Nemotron client (OpenAI-compatible API): retries, timeouts, key safety | FR-2, FR-7 |
| `prompts.py` | Builds prompts: secret redaction, numbered files, injection fencing, source diffs | FR-2, FR-7 |
| `generate.py` | Proposes operations and repairs; repairs can't change an operation's contract | FR-2, FR-7 |
| `extract.py` | tree-sitter symbols for COBOL paragraphs, Java methods and Fortran subroutines/functions, confirmed against the source | FR-1, FR-11 |
| `runtimes.py` | Per-language image, build command, and call command (never from the model) | FR-4, FR-11 |

## Run it

The backend runs anywhere Python 3.11+ and Docker run. Legacy code always runs inside Linux containers, so COBOL and Java (and Fortran) behave the same on every machine.

1. Install Docker (on Windows: Docker Desktop with the WSL2 backend).
2. Build the legacy runtime image once: `docker build -t replic8-legacy-runtime:1 backend/runtime`
3. Install and start the backend from `backend/`:

```bash
pip install -e ".[dev]"
```

```bash
python -m replic8
```

It listens on `http://127.0.0.1:8000`, which is what the web dashboard's dev proxy expects. Set the environment variables below first. On Windows PowerShell use `$env:NAME = "value"`; on macOS, Linux or WSL use `export NAME=value`. WSL2 is the smoothest option on Windows, but native Windows works too.

To generate a token: `python -c "import secrets; print(secrets.token_hex(24))"`.

### Demo walkthrough (local legacy folders)

```bash
export REPLIC8_LOCAL_REPO_ROOT=../legacy
```

Then, with an admin token, onboard both systems:

```bash
curl -X POST http://127.0.0.1:8000/v1/admin/systems -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{"system":"maintenance","repo_url":"local://b-maintenance-cobol","examples":{"get_request":[{"request_id":"R-1001"}],"list_open_requests":[{"well_id":"W-17"}]}}'
```

```bash
curl -X POST http://127.0.0.1:8000/v1/admin/systems -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{"system":"inventory","repo_url":"local://c-inventory-java","examples":{"check_stock":[{"part_id":"PMP-2210"}],"get_shipping_options":[{"part_id":"PMP-2210","destination":"PERMIAN"}]}}'
```

Watch `GET /v1/events`. For the live break, rename `GET-REQUEST` to `FETCH-REQUEST` in `MAINT.cbl` (both places), then `POST /v1/admin/systems/maintenance/check`. In testing with live Nemotron, the repair was saved as v2 in about 6 seconds with identical answers. Undo the rename afterwards (`git checkout legacy/`).

## API (MCP and REST)

| Route | Token | What it does |
|-------|-------|--------------|
| `GET /health` | none | Liveness only |
| `POST /mcp` | gateway or admin | **MCP** (Streamable HTTP, stateless JSON): `initialize`, `tools/list`, `tools/call`. The main interface |
| `GET /v1/operations` | gateway or admin | Published tools (the dashboard reads this; fields unchanged) plus `output_schema` and `contract_cases` |
| `POST /v1/operations/{tool}` | gateway or admin | Call a tool: `{"input": {...}}` returns `{"result", "provenance"}` |
| `GET /v1/openapi.json` | gateway or admin | OpenAPI 3.1 for the enabled tools |
| `GET /v1/graph` | gateway or admin | `{"nodes", "edges"}`; edges of type `data` come from real field names, with `evidence` `schema` or `recorded`. `system_links` has one compact entry per pair of systems (shared `fields`, strongest `evidence`, matching `operation_pairs`) and stays small however many operations match; `edges` is capped at 2000 data links and `truncated` is true when the cap was hit |
| `GET /v1/events?after=N` | gateway or admin | Activity log (onboard_started, onboard_stage, onboarded, published, contract_failed, heal_started, heal_saved, rolled_back, ...) |
| `GET /v1/systems` | gateway or admin | Each system's current version, tests and rejected operations |
| `GET /v1/systems/{s}/versions` | gateway or admin | Version history |
| `POST /v1/admin/systems` | admin | Onboard `{"system", "repo_url", "examples"?, "known_values"?}`. `known_values` maps an input field name to real IDs from the system's data (for example `{"request_id": ["R-1001"]}`); the contract tests use them so they hit real records, and a model-written `pattern` that rejects one is dropped. Returns 422 for a bad URL and 409 if the system is already being processed; otherwise it runs in the background and reports `onboard_stage` events (fetch, detect, build, extract, propose, test, publish), then `published` or `onboard_failed` |
| `POST /v1/admin/systems/{s}/check` | admin | Check the legacy repo for changes; repair if needed |
| `POST /v1/admin/systems/{s}/heal` | admin | Start a repair now |
| `POST /v1/admin/systems/{s}/rollback` | admin | Serve an older version: `{"version": 1}` |

## How trust works

- **Pinned versions:** a published version runs the exact commit it was tested on. A change in the legacy repo never breaks live calls; it's picked up by a check, retested and saved as a new version.
- **Contract tests:** each operation runs in the sandbox with operator and model example inputs. Outputs are recorded, and the published output schema is learned from those real outputs, not guessed by the model.
- **Self-heal:** on new code, every recorded case is replayed first. Only operations that broke go to Nemotron, and a repair is saved only if its replay gives identical outputs. `trigger_heal` also starts this when a live call fails with `FunctionMissing` or `OutputSchemaError`.

## Run the tests

```bash
cd backend
pip install -e ".[dev]"
docker pull alpine:3.20                            # optional: real sandbox tests
docker build -t replic8-legacy-runtime:1 runtime   # optional: COBOL/Java end-to-end tests
pytest -q
```

## Environment variables

| Variable | Meaning |
|----------|---------|
| `REPLIC8_DATA_DIR` | Where clones and the registry live (default `./data`, git-ignored) |
| `REPLIC8_GATEWAY_TOKENS` | Comma-separated bearer tokens for agents and the dashboard, at least 32 characters each. Required. |
| `REPLIC8_TOKEN_SCOPES` | Which tools each token may call: `<token id>=maintenance.*\|inventory.get_part,<token id>=...`. The token id is the first 12 hex characters of the token's SHA-256 (shown in audit logs). A token with no entry can call nothing. |
| `REPLIC8_ADMIN_TOKENS` | Separate tokens for onboarding, repairs and rollback. Admin API is off when empty. |
| `REPLIC8_LOCAL_REPO_ROOT` | Dev/demo only: allow `local://<folder>` repos from this folder. Off when unset. |
| `REPLIC8_POLL_SECONDS` | Check legacy repos for changes every N seconds (at least 30; 0 = off) |
| `REPLIC8_CORS_ORIGINS` | Exact browser origins allowed to call the gateway directly. Not needed with the Vite proxy. |
| `REPLIC8_ALLOWED_HOSTS` | Host headers the MCP endpoint accepts (default `127.0.0.1:*,localhost:*`) |
| `REPLIC8_HOST`, `REPLIC8_PORT` | Where the server listens (default `127.0.0.1:8000`) |
| `REPLIC8_WRITE_OPS` | Write tools to allow, e.g. `inventory.reserve_part`. Leave empty in v1. |
| `REPLIC8_SANDBOX_IMAGES` | Docker images the sandbox may run. Each must be pinned by digest (`name:tag@sha256:...`) or startup fails, and images are never pulled at call time. When unset, startup pins the local `replic8-legacy-runtime:1` image to its current digest. |
| `NVIDIA_API_KEY` | Nemotron API key. Required for generation and healing. |
| `REPLIC8_NEMOTRON_MODEL` | Exact model id, currently `nvidia/nemotron-3.5-super-vl-120b-a12b`. Required. |
| `REPLIC8_NEMOTRON_BASE_URL` | Default `https://integrate.api.nvidia.com/v1` |
| `REPLIC8_NEMOTRON_STRUCTURED` | Default `1`: constrain output with `response_format` (NVIDIA rejects `nvext.guided_json`) |
| `REPLIC8_NEMOTRON_THINKING` | Default `0`. Thinking mode used ~3,700 tokens and cut answers off in testing |

Never commit these values.
