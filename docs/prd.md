# REPLIC8 PRD

Status: draft v0.2 (2026-11-07). Requirement IDs match [requirements](requirements.md). Anything marked **TBD** or **verify** is undecided or unchecked. Don't treat it as fact.

## 1. Problem

Old software has no API and no MCP server, so AI agents can't use it. Rewriting it is slow and risky. REPLIC8 reads a legacy repo and generates a working API and MCP server around it, so agents can call it today.

## 2. Goal

Turn legacy source code from GitHub into an agent-ready API and MCP server, keep it working when the legacy code changes, and show how several systems connect.

**Hackathon success looks like (24h):** a live demo where REPLIC8 converts two legacy systems, a modern parent company's AI agent gets answers from both through one gateway, we see the connections in a graph, then we rename something in the legacy code and watch REPLIC8 repair the integration and show it in the dashboard's activity feed. Company A's agent connects over MCP.

## 3. Users

- **Primary:** a company (like Company A below) that acquires businesses and inherits their old software.
- **Secondary:** an AI agent that calls the generated tools.

## 4. Demo scenario

**Company A** is a modern parent company with its own modern platform, API, and AI agents. It acquires two businesses and inherits their legacy software, which has no usable APIs.

| Company | What it does | Legacy software it brings |
|---------|--------------|---------------------------|
| A: modern parent | Coordinates purchasing, operations, reporting, and technology across subsidiaries | None (modern platform and AI agents) |
| B: oilfield services | Services wells and maintains field equipment | Maintenance, equipment, procurement |
| C: industrial logistics/manufacturing | Makes replacement parts and moves equipment | Inventory, production, shipment |

REPLIC8 is the integration layer. It connects **legacy to modern** (A to B, A to C) and **legacy to legacy** (B to C).

**Demo flow:**
1. A replacement-pump request is recorded in B's legacy maintenance system.
2. A's platform uses a generated tool to retrieve that request.
3. Another generated tool checks C's inventory.
4. A combines the results to show available parts and delivery options.
5. We rename a function or field in a legacy repo. The integration breaks, REPLIC8 validates a repair, saves a new version, and the dashboard's activity feed shows each step.

**Authorization rule:** v1 only does lookups and recommendations (read-only). Purchasing or dispatching are write operations and stay disabled until explicitly authorized.

## 5. Features

### F1. Legacy code to API/MCP (FR-1 to FR-5, FR-11, FR-13)
1. User gives a GitHub repo URL.
2. REPLIC8 clones it and detects the language. **It must work on any language**, using three tiers (FR-11):
   - **Parsed:** a tree-sitter grammar exists, so we extract the real functions and signatures. The LLM only sees extracted symbols, not guesses.
   - **Inferred:** no grammar, so Nemotron reads the files and proposes entry points. Less trustworthy, so it relies entirely on the contract tests below.
   - **Black-box:** code can't be understood, so we wrap it as a command (args, stdin/stdout) or HTTP service and test it from the outside.

   Each operation is labeled `parsed`, `inferred` or `black-box` so users know how much to trust it.

   **Language coverage (decided 2026-11-07, to build).** The promise is *read any old language, run the ones we can build and test*. Reading is the model's job; running needs a free compiler or interpreter in the sandbox, and some languages (RPG, PL/I, mainframe dialects) have none. We add: (a) C and Pascal compilers and Python 3, Perl and PHP interpreters to the sandbox image; (b) a generic caller for interpreted languages, which calls a function by name with JSON arguments; (c) a **command-line wrapper** for any program that runs from a command line, where the model fills in a fixed form (argument template and how to read the output) and REPLIC8 validates it and builds the command. The model never writes code. A language with no toolchain stops at "no supported language yet"; a spec-only mode is not planned.
3. Nemotron picks which functions to expose and writes the wrapper: an MCP server (the main interface for agents) and a REST API (OpenAPI) with the same tools. Each operation is marked `read` or `write`; **write operations are disabled by default** (FR-13).
4. Every exposed operation must point to a source location (`file:line`) and pass a contract test against the real legacy code. Operations that fail are not published.
5. The legacy code runs in a sandbox (Docker), never directly on the host.
6. Several systems register into one gateway with namespaced tools, e.g. `maintenance.get_request`, `inventory.check_stock`.

Reference: [api-anything](https://github.com/goodnight000/api-anything) is the model for the learn, call, repair loop, the MCP/OpenAPI outputs, and "save only after a replay works." It works on websites, not source code, so we reuse the ideas, not the code.

### F2. Self-healing (FR-7, FR-8)
Triggered when a wrapper breaks, meaning its contract tests fail after the legacy code changes (e.g. a renamed function or field):
1. Detect the failure (scheduled test run, or a new commit on the legacy repo).
2. Nemotron compares the old wrapper with the current source (the git diff) and diagnoses what changed.
3. Regenerate the wrapper, replay the contract tests, and **save only if they pass**.
4. Store it as a new version; keep the old one for rollback.
5. Record each step in the activity log, which the dashboard shows (F5).

**In the dashboard (decided and built 2026-11-07):** each system shows its version history (v1, v2, ... with reason, commit and test results), a **Check for changes** button, a **Repair now** button and a **Roll back to vN** button, plus a live activity feed read from `GET /v1/events`. Detection is by button only, not by timer, so the demo is predictable: edit the legacy repo, click the button, watch the repair, see the new version, and confirm the tools still answer. These actions need the admin token, held in browser memory only.

No screenshots or vision model in v1.

### F3. Graph visualization (FR-6)
A web view of the unified API: nodes for companies/systems and operations, edges for shared data and calls between systems (A to B, A to C, B to C). Edges come from matching schemas (real field names/types, e.g. a shared part ID), not LLM guesses.

### F4. Extend (FR-9)
Add new functionality that doesn't touch the legacy code, such as a new endpoint that combines data from two systems. Lives in a separate `extensions/` module. **Decided 2026-11-07:** in the 24-hour build, an extension repo can be imported and registered, and shows in the graph labeled "not run yet". Running extension code is not built. **Changed 2026-11-07:** dropped from the hackathon build and the Extension tab removed. Combining systems happens in the customer's own agent, which calls REPLIC8's tools for each system and joins the answers. Engineer-defined combine recipes are a possible later feature.

### F5. Status updates (FR-12: Photon dropped)
Photon was dropped (2026-11-07). Status events go to the activity log (`GET /v1/events`), which the dashboard shows. No texts are sent and nothing is received.

- **Events logged:** system onboarded, wrapper published, contract failed, change detected, self-heal started, repair saved as a new version, repair failed, rolled back.
- **Safe content:** identifiers, versions, counts and fixed event kinds only. Never source code, secrets, tokens, or raw customer data.
- **Non-blocking:** recording an event never stops a conversion or repair.
- **Noise control:** group repeated failures into one message.

### F6. Dashboard (FR-6, WEB-4, WEB-8 to WEB-13)
The web app in `web/`. Built: graph of systems, operations and links (collapses for hundreds of operations), operations table, and **Import from GitHub** with live stages and known-good values. Decided 2026-11-07. Heal and versions and the real activity feed are built; the rest is still to build:
- **Heal and versions:** see F2 (built).
- **Connect screen** (a new item in the sidebar): the gateway address and copy-paste setup for an agent (Claude Code, a generic MCP client config, a curl example). The token appears as a placeholder, with no "copy with my token" button.
- **Try it:** on each operation, fill in the inputs from the schema, run a live read-only call, and see the result and where it came from.
- **Established system import (built 2026-11-07):** import a modern system (like Company A) from GitHub; REPLIC8 reads its OpenAPI file (YAML or JSON) from the repo, lists its operations and shows it as a node in the graph, labeled "listed only, never called". A **This is the parent company** checkbox draws a line from it into REPLIC8. Re-importing replaces the saved copy.
- **Extension import:** dropped (see F4).
- **Real activity feed:** replaces the simulated entries.

## 6. Architecture

```mermaid
flowchart LR
  GH[GitHub repos: B and C] --> ING[Ingest: clone + tree-sitter]
  ING --> GEN[Generate: Nemotron]
  GEN --> VER[Verify: contract tests in Docker]
  VER -->|pass| REG[Registry: versioned wrappers]
  VER -->|fail| GEN
  REG --> GW[Gateway: REST + MCP, read-only default]
  GW --> A[Company A platform and agents]
  REG --> UI[Graph UI]
  GH -. code change .-> HEAL[Heal: Nemotron]
  GW -. failing tests .-> HEAL
  HEAL --> GEN
  HEAL -. events .-> UI
```

## 7. Security interfaces

Everyone must use these functions.

| Function | Status | When to use | Rules | Owner |
|----------|--------|-------------|-------|-------|
| `Validator.validate_call(token, tool_name, args)` (`backend/replic8/validator.py`) | Built | At the start of every gateway route (REST and MCP). | REST and MCP both use it. Raises `Denied` with 401 for a bad token, 403 on admin routes for a non-admin token (admin tokens, `REPLIC8_ADMIN_TOKENS`, are separate and unscoped), 429 over the rate limit, 403 if the tool is outside the token's scopes (`REPLIC8_TOKEN_SCOPES`; no scopes means no access) or is a write operation, 404 if the tool isn't published, 413 over 64 KB, 422 for bad input. Logs every call to the audit log. | Security |
| `Sandbox.run(image, code_dir, argv, payload)` (`backend/replic8/sandbox.py`) | Built | Any time B or C legacy code runs (contract tests, gateway calls, heal retests). Never run legacy code directly. | Each call gets a fresh, locked Docker container (B = GnuCOBOL): no network, read-only, non-root, resource limits, timeout. Images are pinned by digest and never pulled at call time. Raises `SandboxError` (base error) for setup problems. Timeouts and crashes are reported as result fields (`timed_out`, `exit_code`, `output_too_large` on `SandboxResult`) that the error handler reads. The executor turns those fields into `SandboxTimeout` and `SandboxCrash`, and wrong output or a renamed function into `OutputSchemaError` and `FunctionMissing` (all built). `Sandbox.build` compiles legacy code through `Sandbox.run` with only the build folder writable. | Security |
| `trigger_heal(tool_name, error_info)` (`Pipeline` in `backend/replic8/pipeline.py`) | Built | Called by the error handler only on `OutputSchemaError` or `FunctionMissing`. | A repair must not change a tool's read/write access, and is saved only if contract tests pass. | Backend |
| ~~`notify(event, *, system, version, count)`~~ | Removed 2026-11-08 | Photon was dropped; status goes to the activity log (`EventLog` in `backend/replic8/events.py`). | Events carry only identifiers, versions, counts and fixed kinds; no code or data. | Security |

## 8. Technology choices

| Area | Choice | Why | Check |
|------|--------|-----|-------|
| Backend | Python + FastAPI | Auto-generates OpenAPI; easy to run legacy code as subprocesses | |
| MCP | Official MCP Python SDK | Same language as backend | verify current SDK API |
| Code parsing | tree-sitter | Real symbols reduce hallucination | confirm grammars for demo languages |
| Code analysis/generation/healing | Nemotron via NVIDIA API | Your chosen model; the only model in v1 | **TBD** model name, rate limits, key |
| Sandbox | Docker | Isolates untrusted legacy code | |
| Registry/versioning | Files + git in a `registry/` folder | No database to set up in 24h | |
| Graph UI | React + React Flow | Fast node/edge graphs | |
| Hosting | Vercel (frontend) and one Azure Ubuntu 24.04 VM with Docker and Caddy (backend) | Simplest for a demo; Azure for Students gives a $100 credit with no card | **Decided: Azure only** (Jai, 2026-11-07; Vultr, DigitalOcean and AWS are not used). The hosting guide and setup are in `deploy/README.md` and `deploy/vm/` (Aryan, 2026-11-08): a Standard_B2s VM (2 vCPU / 4 GB; the free 1 GB B1S size is too small for compiling COBOL and Java), ports 22 (from your IP), 80 and 443 open, and the VM's free Azure DNS name (`<label>.<region>.cloudapp.azure.com`) as the HTTPS hostname for Caddy. `deploy/vm/setup.sh` is plain Ubuntu 24.04. Student subscriptions can limit regions and VM sizes (to verify when creating the VM). Fallback: laptop plus a free Cloudflare quick tunnel. |
| Sandbox languages | COBOL, Fortran, Java today; adding C, Pascal, Python 3, Perl, PHP | "Read any, run what we can" (F1) | **Decided 2026-11-07**; image size grows (the current image is about 1 GB) |
| Notifications | Photon (iMessage, SMS/RCS fallback) | Your chosen service; texts a project owner without building messaging | **verify** pricing, rate limits, whether a send-only key exists, number provisioning | **Dropped 2026-11-08.**

## 9. Anti-hallucination rules (for humans and AIs)

- No operation without a source location and a passing test.
- Graph edges come from schemas, not from model opinion.
- If the docs don't say it, ask or log it under open questions. Don't invent.

## 10. 24-hour scope

| Priority | What | Reqs |
|----------|------|------|
| P0 | Modern Company A stand-in plus legacy systems B and C, ingest, generate, verify, gateway, MCP + REST | FR-1 to 5, 10, 11, 13 |
| P0 | Graph showing A, B, C and their links | FR-6 |
| P1 | Rename a function/field, auto-repair, new version saved | FR-7, 8 |
| P1 | Dashboard heal and versions (check, repair, roll back) and a real activity feed | FR-7, 8, WEB-10 |
| P1 | Connect screen and Try it | WEB-11, WEB-12 |
| P1 | Language coverage: command-line wrapper, interpreted-language caller, C, Pascal, Python 3, Perl, PHP | FR-11, FR-14 |
| P1 | Established import tab (Extension dropped 2026-11-07) | FR-15, WEB-13 |
| ~~P1~~ | ~~Photon send-only text updates on key events~~ (dropped 2026-11-08) | FR-12 |
| Stretch | Running extension code; extra legacy modules | FR-9 |

Suggested order: build the demo systems and ingest, then generate and verify, then gateway, then graph, then self-healing, then polish the demo script. Keep each legacy system to 2 or 3 read operations.

## 11. Open questions

- [x] Which languages for B and C? **Decided 2026-11-07:** B is COBOL, C is Fortran. Both have tree-sitter grammars, so both can be `parsed`. Both demo systems use the `parsed` tier (Aryan, 2026-11-07); a `black-box` Fortran path is a stretch goal if time allows. **Changed 2026-11-08:** C is now legacy Java (see requirements decisions).
  Original question: To prove "any language," one should be `parsed` (has a tree-sitter grammar) and one should go through the `inferred` or `black-box` tier. Both need a simple Docker image.
- [x] Which Nemotron model, and what API limits and key do we have? **Decided 2026-11-07:** `nvidia/nemotron-3.5-super-vl-120b-a12b` (early access). Key is in Aryan's cloud environment secrets, not the repo. Rate limits still unknown.
- [x] Which cloud provider and who owns the keys? **Decided 2026-11-07 (Jai):** Vercel (frontend) and an Azure for Students VM (backend), Azure only; this replaces the 2026-11-08 Vultr choice. The hostname is the VM's free Azure DNS name (Aryan, 2026-11-08). Still open: who holds the Azure subscription and the admin token.
- [ ] What shared key links B and C (e.g. a part ID) so the graph edge and the combined answer are real?
  **Proposed 2026-11-08 (in the demo systems):** part ID (e.g. `PMP-2210`) and site region (e.g. `PERMIAN`). See `legacy/README.md`. Team to confirm.
- [x] Should each demo legacy system live in its own GitHub repo, so REPLIC8 ingests it by URL? **Decided 2026-11-07:** yes. `legacy-b-maintenance-cobol` and `legacy-c-inventory-fortran` are published as public repos under `jaiom-rola-sp`. The Java version of C stays in `legacy/` for now; the Fortran repo stands in for C when importing from GitHub.
- [x] Where does the "combine B and C" step live: in Company A's agent, or as a cross-system operation inside REPLIC8? **Decided 2026-11-07:** in the customer's agent. REPLIC8 makes each system callable; the agent combines the answers.
- [ ] Team roles: who owns ingest, generation, gateway, graph UI, the demo systems?
- [ ] Security: who can call the gateway (token auth)? What data never leaves the machine? How are write operations authorized later?
- [x] ~~Photon: do we have an account and API key? Does it give us a send-only credential? Which number sends, and which receives?~~ Photon dropped 2026-11-08.
- [x] ~~Photon: which events are worth a text, and how often before it becomes spam?~~ Photon dropped 2026-11-08.
- [x] Proposed (backend): Nemotron never writes code. **Decided 2026-11-07** after live testing (see requirements decisions). REPLIC8 builds each call itself, so we need a small call shim per language (COBOL, Fortran).
- [ ] Do the demo legacy systems need a writable database or folder? The sandbox is read-only and offline by default.
- [ ] Registry history: plain versioned files (built) or also a git commit per version (PRD section 8)?
- [ ] Who holds the gateway tokens, and do we need per-caller scopes after the demo? **Update 2026-11-08:** per-token scopes are built (`REPLIC8_TOKEN_SCOPES`, fail-closed).
- [ ] **Scopes versus dashboard import (found 2026-11-07).** A system imported from the dashboard is invisible to the dashboard's own token until an operator adds `<namespace>.*` to that token's scopes and restarts. Options: show an honest message after import (minimal); an admin-only "grant scope" action; or an opt-in list of token ids that are granted every newly imported system.
- [ ] Where do the legacy systems' real data live for a real customer? **Assumed 2026-11-07 (Claude's recommendation, not yet confirmed by the team):** for the hackathon the data sits in the repo. For customers, a small runner inside the customer's network next to the legacy data, connected outbound to a cloud control plane, goes in the roadmap (`docs/architecture.md`).
- [ ] One deployment per customer or shared hosting? **Assumed 2026-11-07:** one deployment per customer (simplest and safest); the hackathon has one customer, Company A.

## 12. Risks

- "Any language" is a goal, not a guarantee. We prove it on the demo languages and label confidence per operation. Old languages also need their toolchain in the sandbox (picking the right Docker base image per repo is hard).
- Running legacy code from a repo is risky, so sandbox everything.
- Generated wrappers can be wrong in subtle ways, which is why tests gate publishing.
- 24 hours is tight. Cut F4 first, then extra systems.
- Model API outages or rate limits during the demo. Keep a recorded fallback.
- Each new language and the command-line wrapper widen what runs in the sandbox and grow the image. Every new runtime needs its own contract tests and a pinned image, and the model must stay declarative (it fills in forms; REPLIC8 builds the commands).
- The Azure for Students credit needs a valid school email, expires after a year, and can limit regions and VM sizes. Keep the laptop plus tunnel fallback ready.
