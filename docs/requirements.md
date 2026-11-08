# Requirements

Narrative and design: see [prd](prd.md).

## Project summary

REPLIC8 turns legacy source code from GitHub into an agent-ready API and MCP server, keeps it working with self-healing, and visualizes how multiple legacy systems connect to each other and to a modern parent company.

## Goals

- [ ] Convert 2 legacy systems (Subsidiaries B and C) into one unified, read-only API/MCP that Company A's platform and agents can call.
- [ ] Show the connections (A to B, A to C, B to C) in a graph.
- [ ] Auto-repair a wrapper after a rename in the legacy code, save a new version, and show it in the dashboard.

## Functional requirements

| ID | Requirement | Priority | Status | Notes |
|----|-------------|----------|--------|-------|
| FR-1 | Ingest a GitHub repo in any language: clone, detect language, extract functions (tree-sitter when a grammar exists) | Must | Built | GitHub or local demo repos; COBOL, Java and Fortran parsed with tree-sitter |
| FR-2 | Generate a REST API (OpenAPI) and an MCP server per legacy system; each operation traces to `file:line` | Must | Built | MCP at `/mcp` is the main interface for agents; REST and OpenAPI (`/v1/openapi.json`) serve the same tools |
| FR-3 | Contract tests run against the real legacy code; failing operations are not published | Must | Built | Recorded input/output cases; output schema learned from real outputs |
| FR-4 | Run legacy code in a Docker sandbox | Must | Built | Also compiles legacy code in the sandbox |
| FR-5 | Gateway unifies multiple systems under one API/MCP with namespaced tools | Must | Built | MCP first; REST and MCP share `validate_call` |
| FR-6 | Graph UI of companies/systems, operations, and links between them (edges from schemas) | Must | UI preview | React Flow workspace in `web/`; example links clearly labeled, backend `/v1/graph` now serves real schema edges; UI still shows registration only |
| FR-7 | Self-healing: detect failing tests or a changed legacy repo, Nemotron diagnoses against the source diff, regenerate, replay tests, save only on pass | Should | Built | Tested live: rename in COBOL repaired and saved as v2 in about 6s |
| FR-8 | Version history and rollback of wrappers | Should | Built | `/v1/systems/{s}/versions`, admin rollback |
| FR-9 | Extension module: add functionality separate from legacy code | Could | Not started | Stretch |
| FR-10 | Build the demo: a modern Company A stand-in (own API + agent) and 2 legacy systems (B: oilfield services, C: logistics/manufacturing), each with 2 to 3 read operations | Must | Built | B in COBOL, C in legacy Java (`legacy/`); Company A stand-in still to do |
| FR-11 | Language-agnostic ingestion with 3 tiers: parsed, inferred (LLM), black-box (CLI/HTTP wrapper). Label each operation with its tier; every tier must pass contract tests | Must | Partly built | `parsed` tier only; `inferred` and `black-box` not built |
| FR-12 | Send-only status updates to allowlisted phone numbers (e.g. project owner) via Photon on key events (published, failure, heal start/success/fail). No inbound handling, no secrets or code in messages, a failed send never blocks the pipeline | Should | Dropped | Not building Photon (2026-11-08). Status is in `GET /v1/events` and the dashboard |
| FR-13 | Operations are marked read or write; write operations are disabled by default and need explicit authorization | Must | Built | Write ops blocked (403) and not published in v1 |

## Website review requirements

- **WEB-1:** A black, starry landing page with white and silver accents, continuously moving stars at different depths, and a scroll story inspired by the supplied reference.
- **WEB-2:** Hero heading is REPLIC8; its 8 becomes a moving infinity object followed through the story, with a visible idle float and rotation.
- **WEB-3:** Generate the silver sculpture and space background through Higgsfield MCP; retain assets locally and present them for review.
- **WEB-4:** Provide a separate app dashboard with an interactive graph, systems, operations, and activity. Mark demo data clearly and connect only APIs that exist.
- **WEB-5:** Support mobile layouts, keyboard use, and reduced motion; keep the result local for review before publication.
- **WEB-6:** Increase star density and tie hyperspace speed and streak length to scroll velocity, settling to ambient drift when scrolling stops.
- **WEB-7:** Choreograph the 8 with spins, changing depth and scale, and a reversible camera passage through one loop between story chapters. Keep normal scrolling and provide a restrained reduced-motion path.

## Non-functional requirements

- **Traceability:** every generated operation links to source and a passing test.
- **Security:** legacy code runs only in the sandbox; no secrets in the repo; gateway needs a token.
- **Performance:** a demo conversion should finish fast enough to show live (target TBD).

## Out of scope

- Converting GUI-only apps with no source code.
- Screen or vision-based healing (Gemini Vision): dropped for v1.
- Write operations such as purchasing or dispatching in v1.
- Production-grade multi-tenant hosting.
- Photon text notifications (dropped 2026-11-08; the dashboard's activity feed shows status instead).

## Open questions

See [prd section 11](prd.md#11-open-questions).

## Decisions

- **2026-11-08:** Subsidiary C's legacy system is legacy Java (J2SE 1.4 style), not Fortran. Reason: Fortran reads more like a scripting/numeric language than business software; old Java is a more believable legacy system for an inventory company. Same operations, data and shared keys (part ID, site region). REPLIC8 still supports Fortran. B stays COBOL, and the live self-heal rename stays in COBOL.
- **2026-11-08:** Example inputs given at onboarding are treated as real values: if the model's input rules reject them, REPLIC8 loosens only those value rules (pattern, length, enum) and logs a `schema_adjusted` event. Reason: in live testing Nemotron wrote a `part_id` pattern that rejected the real ID `PMP-2210`.
- **2026-11-08:** Photon text notifications are dropped. Reason: team decision to focus scope; the dashboard's activity feed shows status instead.
- **2026-11-08:** MCP is the main interface for agents and the demo. The REST API (with OpenAPI) stays, serving the same tools through the same checks, so we can show it if judges ask.
- **2026-11-08:** The product name is written REPLIC8 everywhere it appears as a name. Code identifiers stay lowercase where tooling needs it (Python package `replic8`, Docker tags, paths, storage keys). Reason: Aryan's call; matches the renamed GitHub repo.
- **2026-11-08:** Published versions are pinned to the commit they were tested on; legacy changes are picked up by a check, retested, and saved as a new version. Reason: agents never see a half-broken tool, and every answer has a tested commit.
- **2026-11-08:** Output schemas are learned from real contract-test outputs, not taken from the model. Reason: in live testing Nemotron guessed wrong types and list names for the COBOL output.
- **2026-11-08:** Admin actions (onboard, repair, rollback) need a separate admin token. Reason: an agent's gateway token should never be able to change what's published.
- **2026-11-07:** Demo legacy languages: Subsidiary B (oilfield maintenance) is written in COBOL, Subsidiary C (logistics/manufacturing) in Fortran. Reason: Aryan's call; both are classic legacy languages. Both have tree-sitter grammars, so both use the `parsed` tier; a `black-box` path for Fortran is a stretch goal. The live rename for self-healing happens in the COBOL system. *(Superseded 2026-11-08: C is now legacy Java.)*
- **2026-11-07:** Nemotron model for generation and healing: `nvidia/nemotron-3.5-super-vl-120b-a12b` via `https://integrate.api.nvidia.com/v1`. Reason: it's the endpoint on our key. Tested live: about 2s per proposal with thinking off; NVIDIA rejects `nvext.guided_json` but accepts `response_format`. It is early access, so keep a fallback model.
- **2026-11-07:** The model never writes code or commands. It only picks functions and describes their inputs and outputs; REPLIC8 builds each call itself. Reason: in live testing the model put inline Python into the command, which both broke its JSON and meant running model-written code.
- **2026-11-07:** Demo is a parent company (A, modern) plus two legacy subsidiaries (B oilfield services, C logistics/manufacturing). REPLIC8 connects legacy to modern and legacy to legacy. Reason: a believable acquisition story that shows both connection types.
- **2026-11-07:** Gemini Vision is dropped. Only Nemotron is used, reading the legacy codebases. Self-healing is driven by failing tests and code diffs, not screenshots. Reason: the team doesn't need vision, and it saves build time.
- **2026-11-07:** The live break is renaming a function or field in the legacy code. Reason: scripted, reliable, and rehearsable.
- **2026-11-07:** v1 is read-only (lookups and recommendations). Reason: purchasing or dispatching would need extra authorization.
- **2026-11-07:** REPLIC8 should handle any legacy language. Defined as 3 ingestion tiers (parsed, inferred, black-box) with a confidence label per operation, not a promise that every repo works. Reason: nobody can guarantee "any," but tiers plus mandatory contract tests keep it honest.
- **2026-11-07:** Project owner notifications go through Photon and are strictly outbound. Reason: no inbound path means no way to trigger actions by text, which keeps the system's write access out of messaging. *(Superseded 2026-11-08: Photon dropped.)*
- **2026-11-07:** Python + FastAPI backend, Docker sandbox, React Flow graph. Reason: fastest path to OpenAPI + MCP in 24h.

- **2026-11-07:** Website direction is a silver infinity object on a dark starfield, with a narrative landing page and a separate SaaS workspace. The numeral 8 in REPLIC8 becomes the object followed on scroll. Assets generated through Higgsfield; local review requested before publication.
