# REPLIC8

Turn old code on GitHub into tools that AI agents can use.

Live site: https://www.replic8.work

## Try it

Go to **https://www.replic8.work**, open the dashboard, and choose **Open a workspace**. Pick a demo from the **Try a demo workspace** dropdown, or paste one of these public demo tokens:

| Workspace | Token |
|-----------|-------|
| Demo workspace 1 | `r8w_7At38k5fV5r7xqVtDIoc0wu0PeZ-_AeHih-vzRNFe_Y` |
| Demo workspace 2 | `r8w_GBz1wQu8qdoqNf_2OYeDosDQF4ePwB_ciP49IjrZgbk` |
| Demo workspace 3 | `r8w_acVHbda4G99kovkavp_6rVXmk6vVFAvjZs1ziXCoFRA` |

These tokens are public on purpose. They open shared demo workspaces only (not the gateway), and anyone can see and change what is in them. Please don't import private code. They will be rotated after the demo period.

## What it does

- Paste a GitHub repo of legacy code.
- REPLIC8 reads it and finds what it can do.
- It makes a tested API and MCP tools from that.
- Agents call the tools. The legacy code runs only in a locked sandbox.
- If the legacy code changes, REPLIC8 repairs the tools and saves a new version.
- A dashboard shows every system, tool and link between them.

## What we built

- Import a repo from the dashboard and watch it go live, step by step.
- One gateway for many systems, with names like `maintenance.get_request`.
- Same tools over MCP and REST, plus an OpenAPI file.
- Every tool passes a test against the real code before it is published.
- Self-repair: renames in the legacy code are fixed, and you can roll back.
- Read-only: tools that write are turned off.
- Graph of systems and the data that links them.
- Connect page with copy-paste setup for agents.
- Import of modern systems from their OpenAPI file (listed, never called).

## Many repos, one API

- Import each legacy repo as its own system, like `maintenance` or `inventory`.
- All systems sit behind one gateway: one REST API and one MCP server.
- Every tool is named `system.tool`, so agents never mix systems up.
- REPLIC8 links systems when one tool's output is another tool's input, like a `part_id`.
- The graph shows those links, so you can see how old systems connect.
- A token only sees the systems you scope it to.

## How we know it works

- Every tool is tried against the real legacy code before it goes live. If it fails, it is not published.
- Real answers are recorded, and the output rules are learned from them, not guessed.
- Every call is checked on the way in and on the way out.
- Each tool points to the exact file and line it came from.
- Each tool is labeled by how it was found: `parsed`, `inferred` or `black-box`.
- A repair must give the same recorded answers as before, or it is rejected.
- Each live version stays pinned to the code it was tested on.
- Hundreds of automated tests cover the backend and the dashboard.

## Other features

- You can give real IDs at import, so tests hit real records instead of invented ones.
- Version history with one-click rollback.
- Live activity feed of imports, repairs and failures.
- Try any read-only tool from the dashboard and see where its answer came from.
- Pick how a repo is read: functions, command-line programs, or both.
- Change checks can run on a timer, and a repair starts on its own when code changes.

## Languages

| Language | How it runs |
|----------|-------------|
| COBOL | functions |
| Fortran | functions |
| Java | functions |
| Python | functions, or scripts |
| C | command-line programs |
| Pascal | command-line programs |
| Perl | command-line programs |
| PHP | command-line programs |

- Other languages can be read, but not run yet.

## Safety

- Legacy code runs in Docker with no network, a read-only disk and tight limits.
- The AI never writes code. It only fills in a form that REPLIC8 checks.
- Tokens control who can see which systems.

## Run it

### Start the backend (Windows)

You need Docker Desktop (running), Python 3.11+, and the backend's packages installed once with `pip install -e ".[dev]"` from `backend\`.

1. Put your settings in `backend\.env` (copy `backend\.env.example`). At least `REPLIC8_GATEWAY_TOKENS`, `NVIDIA_API_KEY` and `REPLIC8_NEMOTRON_MODEL`, plus `REPLIC8_CORS_ORIGINS=https://replic8.work,https://www.replic8.work` for the live site. The file is never committed.
2. In PowerShell, from the `backend` folder:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\start.ps1
   ```

3. It loads `.env`, makes an admin token if there is none, checks Docker, rebuilds the sandbox image (a few seconds when nothing changed, several minutes the first time), then shows the **gateway address** (your Tailscale Funnel address) and the **admin token**, copies the admin token to the clipboard, and starts the backend. Wait for `Uvicorn running on http://127.0.0.1:8000`.
4. Leave the window open. Ctrl+C stops the backend; run the script again to restart it. Your systems and workspaces are kept in `backend\data`.

To make the gateway public, run `tailscale funnel --bg 8000` once. In the dashboard, use **Start a new workspace** with the gateway address and admin token, and save the workspace token it shows. The admin token is printed on screen, so start the backend before you share your screen.

On macOS or Linux, see [backend/README.md](backend/README.md).

EASIER*: Try this out if our local tunnel gateway is still running:
   input these values into their respective boxs after clicking "create workspace"
================ REPLIC8 ================
Gateway address : https://replica8.tail6f2f22.ts.net
Admin token     : lEF3z1z_-TU0Rv-TQ9ggS6wV7J0IglNL6ddauX7CKWQ
=========================================

### Everything else

- Backend details and API: see [backend/README.md](backend/README.md).
- Dashboard: see [web/README.md](web/README.md).
- Demo systems (COBOL and Java): see [legacy/](legacy/README.md).

## Docs

- [PRD](docs/prd.md): the plan.
- [Requirements](docs/requirements.md): what we build and its status.
- [Deep dive](docs/deep-dive.md): how each feature works inside the backend.
- [Security](docs/security.md): threats and defenses.
- [Changelog](docs/changelog.md): what changed and why.

---

## Using this repo with Obsidian

1. Install [Obsidian](https://obsidian.md).
2. Clone the repo: `git clone https://github.com/jaiom-rola-sp/REPLIC8.git`
   On Windows, clone into a plain folder such as `C:\Users\<you>\Development`. Don't type `~` in PowerShell paths; it creates a folder literally named `~`, which breaks the frontend dev server.
3. In Obsidian, open **Manage vaults → Open folder as vault** and select the cloned `REPLIC8` folder.
4. Pull the latest changes before you start: `git pull`.

Obsidian's settings live in `.obsidian/`, which is git-ignored, so each person keeps their own layout and plugins.

If you use `[[wikilinks]]`, they won't render on GitHub. Prefer standard `[text](path.md)` links, or turn off **Settings → Files and links → Use [[Wikilinks]]**.

## Website preview

The landing page and app dashboard are in [web/](web/README.md). Run `npm ci` and `npm run dev` from that directory, then open the Local URL printed by Vite. Dashboard data starts in a clearly labeled demo mode.
