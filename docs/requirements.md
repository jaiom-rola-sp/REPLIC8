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
| FR-6 | Graph UI of companies/systems, operations, and links between them (edges from schemas) | Must | Built | Every operation drawn under its system; links between systems from `/v1/graph` `system_links` (real fields, evidence recorded or schema); large systems collapse to a summary node (WEB-9) |
| FR-7 | Self-healing: detect failing tests or a changed legacy repo, Nemotron diagnoses against the source diff, regenerate, replay tests, save only on pass | Should | Built | Tested live: rename in COBOL repaired and saved as v2 in about 6s |
| FR-8 | Version history and rollback of wrappers | Should | Built | `/v1/systems/{s}/versions`, admin rollback |
| FR-9 | Extension module: add functionality separate from legacy code | Could | Planned | 2026-11-07: import and register only, labeled "not run yet"; running extension code is not built |
| FR-10 | Build the demo: a modern Company A stand-in (own API + agent) and 2 legacy systems (B: oilfield services, C: logistics/manufacturing), each with 2 to 3 read operations | Must | Built | B in COBOL, C in legacy Java (`legacy/`); Company A stand-in still to do |
| FR-11 | Language-agnostic ingestion with 3 tiers: parsed, inferred (LLM), black-box (CLI/HTTP wrapper). Label each operation with its tier; every tier must pass contract tests | Must | Partly built | `parsed` tier built for COBOL, Fortran, Java. Promise (2026-11-07): read any language, run what we can build. To build: FR-14 (command-line wrapper, interpreted-language caller, more compilers). Spec-only mode not planned |
| FR-12 | Send-only status updates to allowlisted phone numbers (e.g. project owner) via Photon on key events (published, failure, heal start/success/fail). No inbound handling, no secrets or code in messages, a failed send never blocks the pipeline | Should | Dropped | Not building Photon (2026-11-08). Status is in `GET /v1/events` and the dashboard |
| FR-13 | Operations are marked read or write; write operations are disabled by default and need explicit authorization | Must | Built | Write ops blocked (403) and not published in v1 |
| FR-14 | Run more old languages: add C, Pascal, Python 3, Perl and PHP to one sandbox image; a Python function caller (function by name, JSON arguments; Perl and PHP function callers are a stretch); a command-line wrapper for programs run from a command line (C and Pascal programs, Perl and PHP scripts), where the model fills in a fixed form (argument template, how to read the output) that REPLIC8 validates. The model never writes code. A caller's value may become its own argument, with guards (see decisions) | Should | Partly built | B1 and B2 built 2026-11-07: the image, build step, runtimes, and finding functions in all five languages. Still to build: the Python caller (B3), the command-line wrapper (B4), test repos |
| FR-15 | Established system import: read the OpenAPI file from a public GitHub repo, list its operations, show it as a node in the graph, never call it | Should | Planned | Decided 2026-11-07; needs a "kind" on systems and a spec reader |

## Website review requirements

- **WEB-1:** A black, starry landing page with white and silver accents, continuously moving stars at different depths, and a scroll story inspired by the supplied reference.
- **WEB-2:** Hero heading is REPLIC8; its 8 becomes a moving infinity object followed through the story, with a visible idle float and rotation.
- **WEB-3:** Generate the silver sculpture and space background through Higgsfield MCP; retain assets locally and present them for review.
- **WEB-4:** Provide a separate app dashboard with an interactive graph, systems, operations, and activity. Mark demo data clearly and connect only APIs that exist.
- **WEB-5:** Support mobile layouts, keyboard use, and reduced motion; keep the result local for review before publication.
- **WEB-6:** Increase star density and tie hyperspace speed and streak length to scroll velocity, settling to ambient drift when scrolling stops.
- **WEB-9:** The dashboard stays usable with hundreds of operations: large systems collapse to a summary node that expands to a bounded grid with a "+N more" route to the full list, long lists page, and the gateway sends compact system-level links.
- **WEB-7:** Choreograph the 8 with spins, changing depth and scale, and a reversible camera passage through one loop between story chapters. Keep normal scrolling and provide a restrained reduced-motion path.
- **WEB-8:** Import screen: with a connected gateway, a user imports a public GitHub repo as a legacy system and watches the real stages (import, detect, build, extract, propose, test, publish) with plain failure reasons, and can supply known-good values (real IDs) so contract tests hit real records. Established-system and extension sections are visible but disabled until the backend supports them.
- **WEB-10:** Heal and versions in the dashboard: version history per system, **Check for changes**, **Repair now** and **Roll back to vN** (admin token, kept in memory only), with live progress. Detection is by button only. The activity feed reads the real `GET /v1/events` and replaces the simulated entries. **Built 2026-11-07**, tested live (rename in COBOL, repair saved as v2 in about 10 s, tool still answered, rollback worked).
- **WEB-11:** A **Connect** screen in the sidebar: the gateway address and copy-paste setup for an agent (Claude Code, a generic MCP config, curl). The token is a placeholder; no "copy with my token". **Built 2026-11-07.**
- **WEB-12:** **Try it** on each operation: fill in inputs from the schema, run a live read-only call, show the result and its provenance. **Built 2026-11-07.**
- **WEB-13:** The Established system and Extension import tabs work: Established per FR-15, Extension imports and registers only (labeled "not run yet").

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

- **2026-11-07:** Command-line wrapper: a caller's value may become its own command argument (never a shell string), with guards: a value that starts with `-` is rejected, values are length-limited, printable and schema-checked, REPLIC8 (not the model) chooses the binary, and the sandbox stays offline and read-only. This narrows the earlier rule that caller input never becomes an argument (`models.py`, `docs/security.md`). Krish should review it before the wrapper ships. Reason: most command-line programs take arguments, so stdin-only would cover very little.
- **2026-11-07:** Interpreted languages: Python gets a function-by-name caller now; Perl and PHP run through the command-line wrapper, and function-level Perl and PHP callers are a stretch. One sandbox image holds every runtime (split it per language later if it gets too big). Reason: fewer harnesses to build and test in 24 hours, and old Perl and PHP are usually scripts.
- **2026-11-07:** Build order for the next round: A first (Connect screen, Try it), then B (languages). Reason: A is small and demo-visible, and B is the long job.

- **2026-11-08:** The backend is hosted on an Azure for Students VM (Ubuntu 24.04, Standard_B2s), the student-credit option allowed by the 2026-11-07 hosting decision; the frontend stays on Vercel. The VM's free Azure DNS name (`<label>.<region>.cloudapp.azure.com`) is the backend hostname. The setup script moved to `deploy/vm/` (it is the same plain-Ubuntu script for any host). Reason: Aryan's call; student credit covers it, while Vultr costs about $1 a day.
- **2026-11-07:** Hosting is **Azure only**: the backend on one Azure Ubuntu 24.04 VM (Azure for Students credit), the frontend on Vercel, and the laptop plus a free Cloudflare quick tunnel as the fallback. Vultr, DigitalOcean and AWS are not used. Reason: Jai's call; the student credit needs no card, and the same setup script (generic Ubuntu 24.04, in `deploy/`) should run on an Azure VM. Supersedes the two Vultr decisions below.
- **2026-11-07:** The product promise about old languages is **read any, run what we can**: the model reads any language, and operations become callable only where the sandbox has a toolchain to build and test them. We build the command-line wrapper, add C, Pascal, Python 3, Perl and PHP, and keep the model declarative (it never writes code). A spec-only mode is not included, so a language we can't run still stops at "no supported language yet". Reason: nobody can run every language (some have no free toolchain), and the honest label per operation keeps the claim true. Supersedes the open "any language" wording.
- **2026-11-07:** Company C stays on the existing Fortran repo for GitHub imports; no new Java repo for now. Coverage grows through more languages, not more hand-written demo systems. Reason: the importer only runs programs that speak the line protocol, so a random third-party repo wouldn't run until the wrapper exists.
- **2026-11-07:** The dashboard gets the full heal experience (versions, check, repair, roll back, real activity feed), triggered by a button only. Reason: it's the demo's climax, and a button is predictable on stage. The current Activity feed is simulated and gets replaced.
- **2026-11-07:** The Connect screen (setup snippets) and Try it (live read-only calls) are built. Reason: a parent company's engineers need to see how to use the gateway, and a judge needs to see a real call work.
- **2026-11-07:** Both the Established and Extension import tabs are built. Established reads the repo's API file and never runs it; Extension imports and registers only. Reason: Company A should appear in the real graph, and Extension is the stretch goal.
- **2026-11-07:** Hosting for the demo: the team's earlier choice (Vercel plus a Vultr VM, `deploy/`) stands, but Vultr is not free (about $1 a day for 2 vCPU / 4 GB unless a promo applies). Student-credit VMs (Azure for Students, DigitalOcean via the GitHub Student Developer Pack) are an acceptable alternative host for the same setup script, and the laptop plus a free Cloudflare quick tunnel is the fallback. Reason: free credits cost nothing, and the setup script is generic Ubuntu 24.04. *(Superseded 2026-11-07: Azure only.)*
- **2026-11-07:** No database yet. State is small (versions as files, an event log, rebuildable clones); a persistent volume and backups are enough for one deployment. Postgres is the next step once there are several instances, durable audit, scoped tokens at scale, or several customers. SpacetimeDB is not recommended. Reason: see `docs/architecture.md`.

- **2026-11-08:** Hosting: the frontend on Vercel (Jai), the backend on one Vultr Ubuntu 24.04 server behind Caddy for HTTPS. Setup is scripted in `deploy/`. Reason: team choice; Vercel suits the static React app, and the backend needs Docker, which serverless hosting can't provide. *(Superseded 2026-11-07: Azure only.)*
- **2026-11-08:** Subsidiary C's legacy system is legacy Java (J2SE 1.4 style), not Fortran. Reason: Fortran reads more like a scripting/numeric language than business software; old Java is a more believable legacy system for an inventory company. Same operations, data and shared keys (part ID, site region). REPLIC8 still supports Fortran. B stays COBOL, and the live self-heal rename stays in COBOL.
- **2026-11-08:** Example inputs given at onboarding are treated as real values: if the model's input rules reject them, REPLIC8 loosens only those value rules (pattern, length, enum) and logs a `schema_adjusted` event. Reason: in live testing Nemotron wrote a `part_id` pattern that rejected the real ID `PMP-2210`.
- **2026-11-07:** The dashboard imports from GitHub in three planned sections: Legacy (built), Established (will read the repo's API file and list its operations; never run it), and Extension (will only load and register for now). Public repositories only. Imports need a separate admin token, held in browser memory only. The Fortran demo system will be replaced by an old Java system, which needs a Java runtime in the backend first. Reason: keeps v1 read-only and cheap while the GitHub loading is proven.
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
- **2026-11-07:** Photon is dropped. Notifications are log-only: `Notifier` keeps its log-only transport and no texts are sent. FR-12 moved to out of scope. *(Superseded 2026-11-08: the notifier was removed; status goes to the activity log, `GET /v1/events`.)*
