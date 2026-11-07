# Changelog

Log every meaningful change to the project. Newest entries go at the top.

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
