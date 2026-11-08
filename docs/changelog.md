# Changelog

Log every meaningful change to the project. Newest entries go at the top.

## 2026-11-08: Grant and remove token scopes at runtime

- **Who:** Krish Thapa (with Claude)
- **What changed:** New admin-only `POST` and `DELETE /v1/admin/scopes` (`{"token_id", "scope"}`) grant or remove a gateway token's scope without a restart. Changes take effect immediately for REST calls, MCP calls, and the REST and MCP tool lists. Token ids must be 12 lowercase hex characters and belong to a gateway token (admin tokens are unscoped); scopes must be `ns.*` or `ns.tool`. A runtime grant never covers a write operation: granting a write tool by name returns 422, and a namespace grant opens only its reads; writes still need a `REPLIC8_TOKEN_SCOPES` scope and `REPLIC8_WRITE_OPS`. Every grant, removal and refused write grant is audit-logged with the admin's token id. Changes live in memory, so `REPLIC8_TOKEN_SCOPES` stays the starting config after a restart. In `backend/.env.example`, kept Aryan's `REPLIC8_TOKEN_SCOPES` block and pointed its "then a restart" line at the new endpoints. Added the routes to `backend/README.md`, and `DELETE` to the CORS methods. Updated the scopes notes in `docs/security.md` (known gaps) and `deploy/README.md` to give `POST /v1/admin/scopes` as the no-restart option, with `REPLIC8_TOKEN_SCOPES` kept as the permanent one. 20 tests in `tests/test_scope_admin.py`.
- **Requirement(s):** FR-13
- **Commit:** 803e4c7

## 2026-11-08: Demo script, fallback video, tunnel fallback, scopes template, security gaps

- **Who:** Aryan Mandapati
- **What changed:** Added `docs/demo.md`: pre-show checklist (health, seeding with `onboard-demo.sh`, pinned image, CORS), a timed 4-minute talk track using only built features (dashboard, MCP agent, live COBOL break and repair, roll back), what to do if something fails, and the reset steps. Recorded an 80-second captioned fallback video of that flow against the real stack (shared with the team, not committed). `deploy/README.md`: dropped the remaining Vultr/DigitalOcean note and added the laptop-plus-Cloudflare-quick-tunnel fallback steps. `backend/.env.example`: added `REPLIC8_TOKEN_SCOPES` (quoted, with how to get the token id) and `REPLIC8_LOCAL_REPO_ROOT`. `docs/security.md`: refreshed the known gaps (scopes vs dashboard imports, browser token storage, tunnel exposure, data at rest) and listed the gaps closed since.
- **Requirement(s):** FR-10, NFR Security
- **Commit:** this commit

## 2026-11-07: Hosting is Azure only

- **Who:** Claude (for Jaiom)
- **What changed:** PRD section 8 (hosting row), the cloud-provider open question and the risks line now say Azure only (Azure for Students VM for the backend, Vercel for the frontend, laptop plus tunnel as the fallback), replacing the Vultr choice and the Vultr, DigitalOcean and AWS alternatives. Requirements: new decision, and the two Vultr decisions are marked superseded. `docs/architecture.md` updated. Left alone: `deploy/` (the folder was still named `vultr` then; Aryan has since renamed it `deploy/vm`) and the hosting line in `docs/security.md` (T31), which belong to teammates.
- **Requirement(s):** none
- **Commit:** not committed yet (awaiting approval)
## 2026-11-08: Azure hosting guide, deploy/vm, and Windows path fixes

- **Who:** Aryan Mandapati
- **What changed:** Rewrote `deploy/README.md` for an Azure for Students VM (VM size, inbound rules with SSH limited to your IP, the free Azure DNS hostname, stopping the VM to save credit) and noted Vultr, DigitalOcean and the laptop-plus-tunnel fallback as alternatives. Moved the setup scripts from `deploy/vultr/` to the host-neutral `deploy/vm/` and updated the references. Allowed a literal `~` folder in sandbox mount paths (Windows clones under `C:\Users\<you>\~\...`) and added Windows notes to `readme.md` and `web/README.md`. Kept Jai's live activity feed (WEB-10) as the only one; an overlapping local version was dropped before pushing.
- **Requirement(s):** FR-4, NFR Security
- **Commit:** this commit

## 2026-11-07: Heal and versions in the dashboard, with a real activity feed

- **Who:** Claude (for Jaiom)
- **What changed:** A system's detail panel now shows its version history and has **Check for changes**, **Repair now** and **Roll back** (admin token kept in memory only), plus a status line that follows the system's latest event. The Activity screen and the overview's recent activity now show the gateway's real event log (polled every 2 s) instead of simulated entries; the "Run demo workflow" buttons are hidden when connected. Events that change what is published reload the operations, graph and versions. New files: `web/src/SystemHealth.jsx`, `web/src/liveEvents.js` (+ test). Corrected `web/README.md`, which claimed the dashboard read `/v1/events` before it did. Found: with scoped tokens, a system imported from the dashboard is invisible to the dashboard's own token until an operator adds its scope (open question in the PRD).
- **Requirement(s):** FR-7, FR-8, WEB-10
- **Validation:** 22 web tests and a clean build. Real end-to-end run in headless Chrome against the real backend and real Nemotron, using a local copy of the COBOL system: open the system, check (no change), rename `GET-REQUEST` to `FETCH-REQUEST`, check again, change detected, contract test failed (function no longer found), repair saved as v2 about 10 s later, the tool still answered with the real record served by v2, roll back to v1 worked, and the activity feed showed every step; no page errors. The test system and its files were removed afterwards. Not tested: a repair of a change pushed to a real GitHub repo (the same code path, but the network fetch was not exercised), and a failed repair.
- **Commit:** not committed yet (awaiting approval)

## 2026-11-07: Plan decisions: languages, heal UI, Connect screen, imports, hosting, architecture

- **Who:** Claude (for Jaiom)
- **What changed:** Recorded the team's planning decisions. PRD: language coverage plan (read any language, run what we can; command-line wrapper, interpreted-language caller, C, Pascal, Python 3, Perl, PHP; the model stays declarative), the dashboard heal and versions experience, new F6 (Dashboard: Connect screen, Try it, Established and Extension import), hosting alternatives, scope rows, open questions, risks. Requirements: FR-6 now Built; FR-9 and FR-11 notes updated; new FR-14 (more languages) and FR-15 (Established import); WEB-10 to WEB-13; decisions. New `docs/architecture.md` (how parent companies use it, where it runs, what it stores, why no database yet, why not SpacetimeDB, where legacy data lives, tenancy, phases). Found while doing this: per-token scopes are fail-closed, so a system imported from the dashboard is invisible to the dashboard's own token until an operator adds its scope (open question in the PRD).
- **Requirement(s):** FR-6, FR-9, FR-11, FR-14, FR-15, WEB-10 to WEB-13
- **Commit:** not committed yet (awaiting approval)

## 2026-11-08: Merge Java switch and graph work into the propose prompt

- **Who:** tonia (with Claude Code)
- **What changed:** Merged origin/main (Company C in Java, known-good values, graph scaling). In `prompts.py`, kept the teammate's input-schema rule (strict inputs, no `pattern` unless the code enforces it, IDs may contain hyphens) and removed my overlapping wording; kept my call-protocol, field-name, description and output-schema rules, and the rule that `maxLength` comes from the field size in the code. In `.gitignore`, removed my `.env` block because the teammate's identical block covers it.
- **Requirement(s):** FR-2, FR-6
- **Commit:** this commit

## 2026-11-08: Ignore .env files repo-wide

- **Who:** tonia (with Claude Code)
- **What changed:** `.gitignore` now ignores `.env` and `.env.*` everywhere (previously only under `web/`), keeping `.env.example` files tracked, so a `backend/.env` with the Nemotron key can't be committed.
- **Requirement(s):** NFR Security
- **Commit:** c201d63

## 2026-11-08: Agent-friendly propose prompt

- **Who:** tonia (with Claude Code)
- **What changed:** `prompts.py` rules now explain the call protocol (how input and output keys map to the legacy `KEY=VALUE` lines, `items`, `count`), require field names copied from the legacy keys so systems share names (e.g. `part_id`), and ask for agent-facing descriptions on each operation and property, strict inputs (`maxLength` from field sizes) and lenient outputs. Added `tests/test_prompts.py` (2 tests). Live run on B and C: all 4 operations accepted; known issue: `cost_usd` was typed as a string though the shim returns a number.
- **Requirement(s):** FR-2, FR-6
- **Commit:** c201d63
## 2026-11-08: Merge Jai's connected frontend with the security merge and Vultr deployment

- **Who:** Claude (for Aryan)
- **What changed:** Merged `main` (Jai's dashboard connection, Add System flow, graph layout, onboarding stages and `known_values`) with Krish's security merge and the Vultr deployment. No conflicts; Jai's routes run through the merged `Validator` and token scopes. 159 tests pass, including Jai's new ones.
- **Requirement(s):** FR-5, FR-6, WEB-4
- **Commit:** this commit

## 2026-11-08: Merge Krish's security branch into main

- **Who:** Claude (for Aryan; merging Krish's work)
- **What changed:** Merged the `security` branch. Kept Krish's `Validator.validate_call` (`validator.py`) as the single caller check and extended it with admin tokens; REST and MCP both use it, and tool lists (`/v1/operations`, MCP `tools/list`) show only a token's scopes. Kept per-token scopes (`REPLIC8_TOKEN_SCOPES`, fail closed), digest-pinned sandbox images with `--pull never`, and the stuck-docker-client fix; startup pins the local runtime image to its digest when `REPLIC8_SANDBOX_IMAGES` is unset. Removed `security.py`; kept `notify.py` removed (Photon dropped; status goes to the activity log). Calls that pass validation are now audit-logged too. All of Krish's tests pass alongside main's (145 total).
- **Requirement(s):** FR-5, FR-13, NFR Security
## 2026-11-08: Vultr deployment for the backend; parser hang fix

- **Who:** Claude (for Aryan)
- **What changed:** Added `deploy/` with a guide and a Vultr setup for the backend: `setup.sh` (Docker, Caddy HTTPS, Python, a non-root `replic8` service user, pre-downloaded grammars, runtime image, random tokens, firewall), a hardened systemd unit, a Caddyfile, an env template, `onboard-demo.sh` and `update.sh`. Setup also scopes the generated gateway token to both demo systems and pins the sandbox to the runtime image's digest (Krish's merged rules). Rehearsed the install as a separate service user (health, CORS for a Vercel origin, MCP behind a hostname, onboarding, MCP demo), and re-checked with the merged scopes and pinning. Fixed a hang found while testing: the COBOL grammar never finishes on some garbage input, so each file is now parsed in a time-limited child process (threat T30). Recorded the Vercel + Vultr hosting decision. 146 tests.
- **Requirement(s):** FR-1, FR-5, NFR Security
- **Commit:** this commit

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
## 2026-11-07: Security doc: scopes, digest pinning, no Photon

- **Who:** Krish Thapa (with Claude)
- **What changed:** `docs/security.md`: T9 now covers per-token scopes and `validate_call`; the digest-pinning gap is marked done; the tokens gap no longer says there are no scopes. Removed the Photon items (T13, "the network around Photon", and the Photon transport in "not built yet"). Threat numbers are unchanged, so T13 is now unused.
- **Requirement(s):** FR-4, FR-12 (dropped), FR-13
- **Commit:** a6b9d06

## 2026-11-07: Shared validate_call with per-token scopes

- **Who:** Krish Thapa (with Claude)
- **What changed:** Moved the gateway's auth, rate limit, published-tool, write-blocking, size and input-schema checks into `Validator.validate_call(token, tool_name, args)` in `backend/replic8/validator.py`; every gateway route except `/health` calls it, so a future MCP server can reuse it. Added per-token scopes (`REPLIC8_TOKEN_SCOPES`, `ns.*` or one tool): out-of-scope calls get 403, a token with no scopes can call nothing, and listing shows only in-scope tools. Updated PRD section 7 and the backend README. Added 10 tests.
- **Requirement(s):** FR-13
- **Commit:** 796dd5c

## 2026-11-07: Drop Photon, notifications are log-only

- **Who:** Krish Thapa (with Claude)
- **What changed:** Docs only. Moved FR-12 to out of scope and added a decision that Photon is dropped and notifications are log-only. Updated PRD F5, the `notify` row in section 7, and the notifications row in technology choices. Removed the Photon part of `CLAUDE.md` rule 6. `notify.py` is unchanged (it already defaults to a log-only transport).
- **Requirement(s):** FR-12 (dropped)
- **Commit:** 28a366c

## 2026-11-07: PRD subclass cleanup and Windows test skips

- **Who:** Krish Thapa (with Claude)
- **What changed:** PRD section 7 now lists only `OutputSchemaError` and `FunctionMissing` as planned sandbox subclasses (timeouts and crashes are result fields). The real-container Docker tests and the symlink test now skip on Windows: the sandbox only accepts Linux paths, and symlinks need admin rights on Windows.
- **Requirement(s):** FR-4
- **Commit:** 6836c94

## 2026-11-07: Harden sandbox and notifier

- **Who:** Krish Thapa (with Claude)
- **What changed:** Sandbox: images must be pinned by digest (checked at startup and in `Sandbox`), `docker run --pull never`, and a stuck docker client after a timeout kill no longer raises. Notifier: the transport gets `timeout_s` on every send, the queue is capped (`max_queue`, extras dropped and logged), and `flush()` has a timeout. PRD section 7 now says each call gets a fresh container and that timeouts and crashes are result fields. Added 6 tests.
- **Requirement(s):** FR-4, FR-12
- **Commit:** 10c4517

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
