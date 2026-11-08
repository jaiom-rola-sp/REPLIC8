# Changelog

Log every meaningful change to the project. Newest entries go at the top.

## 2026-11-08: Company C is legacy Java; changelog merges without conflicts

- **Who:** Claude (for Aryan)
- **What changed:** Replaced the Fortran demo system with `legacy/c-inventory-java` (J2SE 1.4 style Java: `checkStock`, `getShippingOptions`; same data and shared keys). Added Java to the runtime image (OpenJDK 17), a sandboxed jar build, a small-JVM call path in the shim, and tree-sitter Java method extraction. Example inputs given at onboarding now override the model's input rules when those reject real values (`schema_adjusted` event). Added `docs/changelog.md merge=union` to `.gitattributes` so simultaneous changelog entries no longer conflict. Tested live with Nemotron: COBOL and Java onboarded, the MCP demo chain answered, and the COBOL rename self-healed to v2. 130 tests.
- **Requirement(s):** FR-1, FR-10, FR-11
- **Commit:** this commit

## 2026-11-07: Graph and lists that scale to hundreds of operations

- **Who:** Claude (for Jaiom)
- **What changed:** A system with more than 4 operations now shows one summary node (counts by tier) that expands to at most 24 operations in a grid plus a "+N more" node that opens the filtered Operations list. The Operations table pages 50 at a time, and the system detail panel lists the first 50 with a link to the rest. Backend: `GET /v1/graph` now returns `system_links` (one compact entry per pair of systems) and caps the per-operation `edges` list at 2000 with a `truncated` flag, because links between operations grow with the square of the count (a shared field like `id` matches everywhere). The graph layout moved to `web/src/graphLayout.js` so it can be tested. Note: the backend still caps each import at 20 operations per system (`MAX_OPERATIONS` in `guard.py`); that limit is unchanged.
- **Requirement(s):** FR-6, WEB-9 (new)
- **Validation:** 135 backend tests pass (6 skipped, need an extra Docker image), including new graph-scaling tests; 16 web tests including a 395-operation layout with no overlapping nodes; the real dashboard was driven in headless Chrome against a mock gateway serving 395 operations across 12 systems (table pages, graph collapses to 25 nodes, expanding shows 24 plus "+96 more", that node opens the filtered list, inspector caps at 50), no page errors; and against the real backend with its 2 systems. Not tested: more than about a dozen systems at once (they are drawn in one row), and a real import producing more than 20 operations per system.
- **Commit:** 63a3329

## 2026-11-07: Graph shows every operation under its system, plus real links

- **Who:** Claude (for Jaiom)
- **What changed:** The dashboard graph drew only one operation per system in demo mode (hardcoded) and none in connected mode (just "2 operations" text). Both modes now draw every operation under its system. Connected mode also reads `GET /v1/graph` and draws a dashed link between systems, labelled with the real field and its evidence (for example `part_id · recorded`). Updated the banner that said graph lines were only registration.
- **Requirement(s):** FR-6, WEB-4
- **Validation:** Real dashboard driven in headless Chrome, no page errors: demo graph shows 2 operations per system; connected graph shows all 4 real operations and the `part_id · recorded` link between maintenance and inventory.
- **Commit:** 63a3329

## 2026-11-07: Fix unusable maintenance tools; known-good values on import

- **Who:** Claude (for Jaiom)
- **What changed:** A live import showed the maintenance tools rejected real IDs like `R-1001` (Nemotron wrote a letters-and-digits-only `pattern`) and that contract tests only ever saw invented IDs ("not found"), so the graph had no link between systems. Fixes: (1) the prompt no longer asks for patterns and warns that real IDs contain hyphens; (2) `POST /v1/admin/systems` accepts `known_values` (field name to real IDs), used as contract-test inputs, and a model-written `pattern` that rejects an operator-supplied value is dropped (types, lengths and the call shim's control-character checks stay; after merging with the Java-switch commit this is done by its `fit_input_schema`, which also loosens length and other value rules); (3) the import form has an optional "Known-good values" box. Re-importing maintenance gave v2 with real records recorded and four `part_id` data edges from maintenance to inventory.
- **Requirement(s):** FR-3, FR-6, WEB-8
- **Validation:** 132 backend tests pass (6 need an extra Docker image and were skipped), including the Docker lifecycle test; 9 web tests; live re-import from GitHub, then real calls: `R-1001` returns part `PMP-2210`, `check_stock` returns 12 on hand, shipping returns 2 carriers; the dashboard form was driven in headless Chrome with no page errors. Not tested: the self-heal rename on the new repos, and whether the pattern-dropping fired in the live run (the model wrote no pattern this time; it is covered by unit tests).
- **Commit:** 63a3329

## 2026-11-07: Import from GitHub in the dashboard, with live stages

- **Who:** Claude (for Jaiom)
- **What changed:** Replaced the "repository draft" dialog with a real import screen (`web/src/AddSystem.jsx`, `web/src/onboarding.js`): system name, public GitHub URL and an in-memory admin token start `POST /v1/admin/systems`, and the stages are shown live from `/v1/events`. Backend: the pipeline now emits `onboard_stage` events (fetch, detect, build, extract, propose, test, publish), reports any unexpected error and a missing Docker as `onboard_failed` instead of failing silently, and the admin endpoint rejects bad URLs (422) and busy systems (409) immediately. Removed the draft code. Established and Extension tabs are shown disabled.
- **Requirement(s):** WEB-8 (new), FR-1, FR-6
- **Validation:** 120 backend tests pass (13 need Docker and were skipped here); 7 web helper tests; a live run against a real gateway imported from GitHub (no-code repo stops at detect, missing repo stops at fetch, this repo reaches build and reports the missing Docker, a non-GitHub URL gets 422); the dashboard was driven in headless Chrome with no page errors. Not tested: a full import through propose, test and publish (needs Docker and a Nemotron key).
- **Commit:** 63a3329

## 2026-11-08: MCP-first backend: contract tests, self-heal, dashboard APIs; Photon dropped; name is REPLIC8

- **Who:** Claude (for Aryan)
- **What changed:** Finished the backend pipeline. Contract tests record real input/output cases and learn output schemas from real outputs. Onboarding (`POST /v1/admin/systems`) fetches, builds, extracts, proposes, tests and publishes. Self-heal replays recorded cases on new code, repairs only what broke, and saves only identical replays; `trigger_heal`, `validate_call` and the `SandboxError` subclasses from PRD section 7 are built. MCP at `/mcp` is now the main interface (added `backend/scripts/mcp_demo.py` and client setup steps); REST and OpenAPI serve the same tools. Added `/v1/graph`, `/v1/events`, `/v1/systems`, version history and rollback for the dashboard (existing `/health` and `/v1/operations` fields unchanged). Admin actions need a separate admin token. Dropped Photon: removed `notify.py` and its setting, and marked FR-12, PRD F5 and threat T13 as dropped. Added local demo repos, change polling, Windows path support, `python -m replic8`, threats T23 to T29, and 128 tests. Tested live with Nemotron: both systems onboarded in about 6 seconds, and a COBOL rename was repaired and saved as v2 in about 6 seconds with identical answers. Renamed the product to REPLIC8 in docs, backend text and the web pages' visible text (identifiers unchanged).
- **Requirement(s):** FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-11, FR-12, FR-13
- **Commit:** this commit

## 2026-11-08: COBOL and Fortran demo legacy systems

- **Who:** Claude (for Aryan)
- **What changed:** Added `legacy/b-maintenance-cobol` (COBOL: `GET-REQUEST`, `LIST-OPEN-REQUESTS`) and `legacy/c-inventory-fortran` (Fortran: `check_stock`, `get_shipping_options`) with fixed-width data linked by part ID and site region. Added the runtime image (`backend/runtime/`: GnuCOBOL, gfortran, call shim, sandboxed build), tree-sitter extraction, and per-language runtimes. Live Nemotron picks exactly the four real operations. Recorded "both systems parsed". Added threats T20 to T22 and 14 tests (109 total), including an end-to-end COBOL and Fortran run through the gateway.
- **Requirement(s):** FR-1, FR-4, FR-10, FR-11
- **Commit:** this commit

## 2026-11-07: CLAUDE.md rule uses Sandbox.run

- **Who:** Krish Thapa (with Claude)
- **What changed:** `CLAUDE.md` rule 6 now says `Sandbox.run` instead of `run_in_sandbox`, to match PRD section 7 and the backend code.
- **Requirement(s):** FR-4, FR-13
- **Commit:** this commit

## 2026-11-07: Security interfaces in the PRD

- **Who:** Krish Thapa (with Claude)
- **What changed:** Added PRD section 7, "Security interfaces", matched to the existing backend: `Sandbox.run`, `SandboxError` (with planned subclasses), `Notifier.notify`, and planned `validate_call` and `trigger_heal`. Renumbered the later PRD sections (Technology choices is now 8, Open questions 11, Risks 12) and fixed the two references to them. Added a `CLAUDE.md` rule to use these interfaces.
- **Requirement(s):** FR-4, FR-12, FR-13
- **Commit:** this commit

## 2026-11-07: Nemotron client, prompts, and self-heal generation

- **Who:** Claude (for Aryan)
- **What changed:** Added `backend/replic8/nemotron.py` (client), `prompts.py` (secret redaction, injection fencing, source diffs) and `generate.py` (propose operations; repairs that keep each operation's contract). Tested live against `nvidia/nemotron-3.5-super-vl-120b-a12b`: switched to `response_format` with thinking off, and the model no longer supplies commands (REPLIC8 builds them). Recorded decisions: B in COBOL, C in Fortran, the model choice, no model-written code. Added threats T15 to T19 to `docs/security.md` and 22 tests (95 total).
- **Requirement(s):** FR-2, FR-7, FR-10, FR-11, FR-13
- **Commit:** not committed yet

## 2026-11-07: Scroll-speed hyperspace and a journey through the loop

- **Who:** Codex (for Jaiom)
- **What changed:** Increased background star density and added scroll-velocity acceleration with bounded radial trails, reverse travel, and smooth deceleration. Added a dedicated passage between Discover and Connect: the silver 8 spins, changes depth and scale, and frames a camera move through one loop. Updated the story navigation and synchronized the starfield’s vanishing point with the passage. Preserved normal scrolling, pause controls, mobile layouts, and a restrained reduced-motion path.
- **Requirement(s):** WEB-1, WEB-2, WEB-5, WEB-6, WEB-7
- **Validation:** Production build and focused browser checks for velocity response, deceleration, reversible portal progress, pause, reduced motion, and mobile layout.
- **Commit:** cfc27f7

## 2026-11-07: Moving stars and visible infinity idle motion

- **Who:** Codex (for Jaiom)
- **What changed:** Replaced the mostly stationary twinkling overlay with continuously moving silver stars at different depths, inspired by the Orizon reference. Increased the silver 8’s float and rotational idle motion while preserving the scroll story. Motion pauses with the existing control, reduced-motion preference, and hidden tabs.
- **Requirement(s):** WEB-1, WEB-2, WEB-5
- **Validation:** Production build and focused browser checks for idle motion, pause/resume, reduced motion, and mobile resize.
- **Commit:** cfc27f7

## 2026-11-07: Silver infinity landing and app review

- **Who:** Codex (for Jaiom)
- **What changed:** Added `web/`, a React/Vite review with a starry black-and-silver scroll story. The hero’s 8 becomes a traveling infinity sculpture. Generated the sculpture and starfield through Higgsfield MCP and retained the assets with provenance. Added a separate responsive React Flow dashboard, operation/source inspection, filters, session-local repository drafts, simulated request tracing, and read-only gateway registry loading through a development proxy. Demo connections remain explicitly illustrative; no ingest, repair, or event-stream endpoints are fabricated. Added web setup documentation and recorded the user’s design requirements.
- **Requirement(s):** WEB-1 to WEB-5, FR-6, FR-10, FR-11, FR-13
- **Validation:** Production build; desktop/mobile browser checks and interaction verification.
- **Commit:** cfc27f7

## 2026-11-07: Backend foundation and security model

- **Who:** Claude (for Aryan)
- **What changed:** Added `backend/` (FastAPI): safe GitHub ingest, hardened Docker sandbox, model-output guard, versioned registry that only publishes tested operations, token-protected read-only gateway, send-only notifier. Added `docs/security.md` (threats T1 to T14 and known gaps) and 73 tests. Added open questions to the PRD.
- **Requirement(s):** FR-1, FR-2, FR-3, FR-4, FR-5, FR-8, FR-11, FR-12, FR-13
- **Commit:** this commit

## 2026-11-07: Stricter git rule for AIs

- **Who:** Claude (for Aryan)
- **What changed:** `CLAUDE.md` rule 4: no `git add`, `commit`, or `push` without the user's explicit approval each time; automated hooks don't count as approval.
- **Requirement(s):** none (process)
- **Commit:** this commit (with the backend foundation)

## 2026-11-07: Keep graphify local

- **Who:** tonia (with Claude Code)
- **What changed:** Added `.graphifyignore` and `graphify-out/` to `.gitignore` so graphify stays local and out of the repo.
- **Requirement(s):** None
- **Commit:** f88a3cb

## 2026-11-07: Demo scenario, drop vision, read-only default (PRD v0.2)

- **Who:** Claude (for Jaiom)
- **What changed:** Added the Company A / Subsidiary B / Subsidiary C demo scenario. Dropped Gemini Vision (Nemotron only; healing driven by tests and code diffs). Chose "rename a function/field" as the live break. Added FR-13 (read-only by default) and updated FR-7, FR-10, FR-12. Renumbered PRD sections; open questions are now section 10.
- **Requirement(s):** FR-7, FR-10, FR-12, FR-13
- **Commit:** b2341f3

## 2026-11-07: Photon send-only notifications

- **Who:** Claude (for Jaiom)
- **What changed:** Added feature F5 and FR-12 (send-only Photon updates to a manager), plus a Photon tech row, open questions, and a security requirement.
- **Requirement(s):** FR-12
- **Commit:** fc0d221

## 2026-11-07: Any-language support

- **Who:** Claude (for Jaiom)
- **What changed:** Added FR-11 (3-tier language-agnostic ingestion), updated FR-1 and FR-10, and updated the PRD's F1, open questions, and risks.
- **Requirement(s):** FR-1, FR-10, FR-11
- **Commit:** cd4b491

## 2026-11-07: Draft PRD and fill requirements

- **Who:** Claude (for Jaiom)
- **What changed:** Added `docs/prd.md` (draft v0.1) and filled `docs/requirements.md` with FR-1 to FR-10, decisions, and non-functional requirements.
- **Requirement(s):** FR-1 to FR-10 (all created)
- **Commit:** cbc0ac3

## 2026-11-07: Ignore graphify output

- **Who:** Krish Thapa (with Claude)
- **What changed:** Added `graphify-out/` to `.gitignore` so generated knowledge-graph files stay out of the repo.
- **Requirement(s):** None
- **Commit:** 58fb7ce
