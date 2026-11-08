# Requirements

Narrative and design: see [prd](prd.md).

## Project summary

Replic8 turns legacy source code from GitHub into an agent-ready API and MCP server, keeps it working with self-healing, and visualizes how multiple legacy systems connect to each other and to a modern parent company.

## Goals

- [ ] Convert 2 legacy systems (Subsidiaries B and C) into one unified, read-only API/MCP that Company A's platform and agents can call.
- [ ] Show the connections (A to B, A to C, B to C) in a graph.
- [ ] Auto-repair a wrapper after a rename in the legacy code, save a new version, and text the project owner.

## Functional requirements

| ID | Requirement | Priority | Status | Notes |
|----|-------------|----------|--------|-------|
| FR-1 | Ingest a GitHub repo in any language: clone, detect language, extract functions (tree-sitter when a grammar exists) | Must | Not started | See FR-11 for fallbacks |
| FR-2 | Generate a REST API (OpenAPI) and an MCP server per legacy system; each operation traces to `file:line` | Must | Not started | |
| FR-3 | Contract tests run against the real legacy code; failing operations are not published | Must | Not started | |
| FR-4 | Run legacy code in a Docker sandbox | Must | Not started | |
| FR-5 | Gateway unifies multiple systems under one API/MCP with namespaced tools | Must | Not started | |
| FR-6 | Graph UI of companies/systems, operations, and links between them (edges from schemas) | Must | Not started | |
| FR-7 | Self-healing: detect failing tests or a changed legacy repo, Nemotron diagnoses against the source diff, regenerate, replay tests, save only on pass | Should | Not started | No vision model in v1 |
| FR-8 | Version history and rollback of wrappers | Should | Not started | |
| FR-9 | Extension module: add functionality separate from legacy code | Could | Not started | Stretch |
| FR-10 | Build the demo: a modern Company A stand-in (own API + agent) and 2 legacy systems (B: oilfield services, C: logistics/manufacturing), each with 2 to 3 read operations | Must | Not started | Languages TBD; cover at least 2 tiers |
| FR-11 | Language-agnostic ingestion with 3 tiers: parsed, inferred (LLM), black-box (CLI/HTTP wrapper). Label each operation with its tier; every tier must pass contract tests | Must | Not started | "Any language" is the goal, proven on demo languages |
| FR-13 | Operations are marked read or write; write operations are disabled by default and need explicit authorization | Must | Not started | v1 demo is lookups and recommendations only |

## Non-functional requirements

- **Traceability:** every generated operation links to source and a passing test.
- **Security:** legacy code runs only in the sandbox; no secrets in the repo; gateway needs a token.
- **Messaging is send-only:** Replic8 sends updates through Photon and never reads replies or acts on incoming messages.
- **Performance:** a demo conversion should finish fast enough to show live (target TBD).

## Out of scope

- Converting GUI-only apps with no source code.
- Screen or vision-based healing (Gemini Vision): dropped for v1.
- Write operations such as purchasing or dispatching in v1.
- Production-grade multi-tenant hosting.
- FR-12 (dropped 2026-11-07): send-only status texts via Photon. Notifications are log-only instead.

## Open questions

See [prd section 11](prd.md#11-open-questions).

## Decisions

- **2026-11-07:** Demo legacy languages: Subsidiary B (oilfield maintenance) is written in COBOL, Subsidiary C (logistics/manufacturing) in Fortran. Reason: Aryan's call; both are classic legacy languages. Both have tree-sitter grammars, so both can use the `parsed` tier (see open questions).
- **2026-11-07:** Nemotron model for generation and healing: `nvidia/nemotron-3.5-super-vl-120b-a12b` via `https://integrate.api.nvidia.com/v1`. Reason: it's the endpoint on our key. Tested live: about 2s per proposal with thinking off; NVIDIA rejects `nvext.guided_json` but accepts `response_format`. It is early access, so keep a fallback model.
- **2026-11-07:** The model never writes code or commands. It only picks functions and describes their inputs and outputs; replic8 builds each call itself. Reason: in live testing the model put inline Python into the command, which both broke its JSON and meant running model-written code.
- **2026-11-07:** Demo is a parent company (A, modern) plus two legacy subsidiaries (B oilfield services, C logistics/manufacturing). Replic8 connects legacy to modern and legacy to legacy. Reason: a believable acquisition story that shows both connection types.
- **2026-11-07:** Gemini Vision is dropped. Only Nemotron is used, reading the legacy codebases. Self-healing is driven by failing tests and code diffs, not screenshots. Reason: the team doesn't need vision, and it saves build time.
- **2026-11-07:** The live break is renaming a function or field in the legacy code. Reason: scripted, reliable, and rehearsable.
- **2026-11-07:** v1 is read-only (lookups and recommendations). Reason: purchasing or dispatching would need extra authorization.
- **2026-11-07:** Replic8 should handle any legacy language. Defined as 3 ingestion tiers (parsed, inferred, black-box) with a confidence label per operation, not a promise that every repo works. Reason: nobody can guarantee "any," but tiers plus mandatory contract tests keep it honest.
- **2026-11-07:** Project owner notifications go through Photon and are strictly outbound. Reason: no inbound path means no way to trigger actions by text, which keeps the system's write access out of messaging.
- **2026-11-07:** Python + FastAPI backend, Docker sandbox, React Flow graph. Reason: fastest path to OpenAPI + MCP in 24h.
- **2026-11-07:** Photon is dropped. Notifications are log-only: `Notifier` keeps its log-only transport and no texts are sent. FR-12 moved to out of scope.
