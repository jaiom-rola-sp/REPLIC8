# Changelog

Log every meaningful change to the project. Newest entries go at the top.

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
- **What changed:** Added `backend/replic8/nemotron.py` (client), `prompts.py` (secret redaction, injection fencing, source diffs) and `generate.py` (propose operations; repairs that keep each operation's contract). Tested live against `nvidia/nemotron-3.5-super-vl-120b-a12b`: switched to `response_format` with thinking off, and the model no longer supplies commands (replic8 builds them). Recorded decisions: B in COBOL, C in Fortran, the model choice, no model-written code. Added threats T15 to T19 to `docs/security.md` and 22 tests (95 total).
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
