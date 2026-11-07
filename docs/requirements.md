# Requirements

Narrative and design: see [prd](prd.md).

## Project summary

Replic8 turns legacy source code from GitHub into an agent-ready API and MCP server, keeps it working with self-healing, and visualizes how multiple legacy systems connect.

## Goals

- [ ] Convert 2 demo legacy repos into one unified API/MCP an AI agent can call.
- [ ] Show the connections between systems in a graph.
- [ ] Auto-repair a wrapper after a scripted break and save a new version.

## Functional requirements

| ID | Requirement | Priority | Status | Notes |
|----|-------------|----------|--------|-------|
| FR-1 | Ingest a GitHub repo in any language: clone, detect language, extract functions (tree-sitter when a grammar exists) | Must | Not started | See FR-11 for fallbacks |
| FR-2 | Generate a REST API (OpenAPI) and an MCP server per legacy system; each operation traces to `file:line` | Must | Not started | |
| FR-3 | Contract tests run against the real legacy code; failing operations are not published | Must | Not started | |
| FR-4 | Run legacy code in a Docker sandbox | Must | Not started | |
| FR-5 | Gateway unifies multiple systems under one API/MCP with namespaced tools | Must | Not started | |
| FR-6 | Graph UI of systems, operations, and links between them (edges from schemas) | Must | Not started | |
| FR-7 | Self-healing: detect failure, diagnose (Gemini Vision + Nemotron), regenerate, replay tests, save only on pass | Should | Not started | |
| FR-8 | Version history and rollback of wrappers | Should | Not started | |
| FR-9 | Extension module: add functionality separate from legacy code | Could | Not started | Stretch |
| FR-10 | Build demo legacy apps: 2 required, 3rd is stretch | Must | Not started | Languages TBD; cover at least 2 tiers |
| FR-11 | Language-agnostic ingestion with 3 tiers: parsed, inferred (LLM), black-box (CLI/HTTP wrapper). Label each operation with its tier; every tier must pass contract tests | Must | Not started | "Any language" is the goal, proven on demo languages |

## Non-functional requirements

- **Traceability:** every generated operation links to source and a passing test.
- **Security:** legacy code runs only in the sandbox; no secrets in the repo; gateway needs a token.
- **Performance:** a demo conversion should finish fast enough to show live (target TBD).

## Out of scope

- Converting GUI-only apps with no source code.
- Production-grade multi-tenant hosting.

## Open questions

See [prd section 9](prd.md#9-open-questions).

## Decisions

- **2026-11-07:** Replic8 should handle any legacy language. Defined as 3 ingestion tiers (parsed, inferred, black-box) with a confidence label per operation, not a promise that every repo works. Reason: nobody can guarantee "any," but tiers plus mandatory contract tests keep it honest.
- **2026-11-07:** Core input is source code from GitHub; demo uses several small legacy apps we build ourselves. Reason: reliable demo we control, and the reference repo (`api-anything`) covers websites, not source code.
- **2026-11-07:** Python + FastAPI backend, Docker sandbox, React Flow graph. Reason: fastest path to OpenAPI + MCP in 24h.
