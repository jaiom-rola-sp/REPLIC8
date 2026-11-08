# REPLIC8 web review

A silver and black scroll story, followed by a separate app workspace. Built with React, Vite, and React Flow.

## Run locally

```sh
cd web
npm ci
npm run dev
```

Open the Local URL printed by Vite (normally http://127.0.0.1:5173).

- Landing: `/`
- Dashboard: `/#/app`
- Production build: `npm run build`
- Inspect a production build: `npm run preview`

The landing’s numeral 8 becomes the same infinity object followed throughout the scroll story. Denser stars accelerate and stretch into trails with scroll velocity, then coast back to ambient motion. The object rolls and changes scale between chapters, with a dedicated scroll-driven passage through one loop before the connected-systems chapter. Scrolling upward reverses the passage. Ambient motion can be paused, and the site respects reduced-motion preferences. The preview is responsive on desktop and mobile.

## Assets

`public/assets/silver-eight.png` and `public/assets/starfield.jpg` were generated through Higgsfield MCP with `gpt_image_2_6`. Their job identifiers and descriptions are recorded in `public/assets/provenance.json`. Both assets are stored in this checkout; the page does not depend on temporary provider URLs. The landing’s Design notes dialog provides a full-resolution asset review.

## Dashboard behavior

The default workspace is an explicitly labeled demo. Its graph, operations, source locations, event stream, metrics, and trace are illustrative. You can inspect graph nodes, pan/zoom, filter systems and tools, and run a simulated request through two systems. No code is cloned or executed and no messages are sent by these interactions.

Gateway settings can load real health and operation-registry data from an existing backend. The default `/gateway` address uses Vite’s development proxy to `http://127.0.0.1:8000`. To use another backend target:

```sh
REPLIC8_GATEWAY_URL=http://127.0.0.1:9000 npm run dev
```

Enter the gateway bearer token in the app’s Settings dialog. It is kept in browser session storage, never in source files or build variables. A connected dashboard reads `GET /health`, `GET /v1/operations`, `GET /v1/graph` and `GET /v1/systems/{system}/versions`, and follows `GET /v1/events` every two seconds for the activity feed.

### Versions, repair and the activity feed

Open a system (Systems, then its card) while connected and the detail panel shows **Versions and repair**:
- the version history, newest first, with the reason (first import, repaired after a change, repaired on request), the commit and how many tools passed their tests;
- **Check for changes**: asks the gateway whether the legacy repo moved past the published commit. If it did, a repair starts in the background; if not, the panel says so (no event is logged when nothing changed);
- **Repair now**: starts a repair directly. It stops right away if the legacy code is unchanged;
- **Roll back** on any older version.

These need the **admin token**, which the panel asks for once and keeps in memory only. The status line at the top of the panel follows the system's latest event, and the **Activity** screen is the gateway's real event log (the "Run demo workflow" buttons only appear in demo mode). Events that change what is published (published, repair saved, rolled back) reload the operations, the graph and the version history by themselves.

Demo for the repair: change the legacy repo (for example rename `GET-REQUEST` to `FETCH-REQUEST` in the COBOL), click **Check for changes**, and watch change detected, contract test failed, repair started, repair saved, then confirm the tools still answer. Rolling back returns to the first version.

Note: gateway tokens are scoped per system and fail closed. A system you import is not visible to the dashboard's token until an operator adds `<system>.*` to `REPLIC8_TOKEN_SCOPES` and restarts the gateway.

### Connect and Try it

- **Connect** (sidebar): how an agent or app uses the gateway. It shows the MCP address and copy-paste setup for Claude Code (`claude mcp add --transport http replic8 <address>/mcp --header "Authorization: Bearer YOUR_GATEWAY_TOKEN"`), a generic MCP JSON config, and two curl examples (list tools, call one tool). The token is always the placeholder `YOUR_GATEWAY_TOKEN`; the real token is never shown. A relative gateway path such as `/gateway` is shown under this site's address, and a local address gets a note that it only works on this computer. It also says how many tools your token can see.
- **Try it** (in an operation's detail panel): a form built from the operation's input schema (text, whole numbers, numbers, true/false, fixed choices; anything nested falls back to a JSON box). Values are checked before sending (required, length, format), then it runs a live read-only call and shows the result and where it came from (version, tier, source file and line, commit, time). Write operations are disabled with a reason, and in demo mode it asks you to connect a gateway. Failed calls are explained by status (bad token, outside the token's scopes, input rejected, rate limit).

The logic lives in `src/connectSnippets.js` and `src/tryIt.js`, tested by `node --test src/`.

### Many operations

The graph stays readable with hundreds of operations:
- A system with up to 4 operations draws each one under it. A bigger system draws **one summary node** (counts by ingestion tier, and how many are disabled writes). Click it to expand to a grid of at most 24 operations, reads first, followed by a **+N more** node that opens the full list. Click the summary again to collapse it.
- Links between systems come from the gateway's compact `system_links`, one dashed line per pair of systems with the shared fields and the evidence.
- The Operations table shows 50 rows at a time (**Show 50 more**), and a system's detail panel lists its first 50 operations with a link to the rest.

The layout lives in `src/graphLayout.js`; `node --test src/graphLayout.test.js` checks it with about 400 synthetic operations. Systems are drawn in one row, so with many more than about a dozen systems you will zoom and pan.

### Import from GitHub

With a gateway connected, **Connect a system** opens the import screen. Without one it asks you to connect first.

1. Choose **Legacy system**, enter a system name (it becomes the tool prefix, like `maintenance`) and a public `https://github.com/owner/repository` URL, optionally list **known-good values** (`request_id=R-1001`, one per line, real IDs from the system's data) so the contract tests check real records instead of invented ones, then enter an **admin token**. The admin token is held in memory only and is never saved.
2. The dashboard posts to `POST /v1/admin/systems`, then polls `GET /v1/events` every second and shows the stages: Import, Detect, Build, Find the functions, Propose, Run contract tests, Publish. A failure marks the stage where the import stopped and shows the backend's reason (for example “no supported language yet” or “the sandbox is unavailable”).
3. When it publishes, the operation list refreshes and the screen reports how many operations were published and rejected.

**Established system** is for a modern system that already has its own API, like the parent company. Enter a name, the repository URL, optionally the path to its OpenAPI file (YAML or JSON), and tick **This is the parent company** if its agents use REPLIC8. The dashboard posts to `POST /v1/admin/established` and shows three stages: Import, Read the API file, Add to the graph. The system then appears above REPLIC8 in the graph (the parent with a line into it) and in Systems; REPLIC8 lists its operations and never calls it. Importing it again replaces the list.

Only public repositories can be imported. Checks that run before anything is sent (URL shape, system name) mirror the backend's rules in `src/onboarding.js`; run its tests with `node --test src/onboarding.test.js`.

Direct HTTP(S) gateway addresses require the backend to allow the browser’s origin. A production deployment needs a same-origin gateway proxy or deliberate CORS configuration; Vite’s development proxy is not part of `dist/`.

## Troubleshooting

- **`403 Restricted ... outside of Vite serving allow list` on Windows:** the project folder's path contains an unusual character (for example a folder literally named `~`, created when a Mac/Linux `git clone ... ~/...` command is run in PowerShell). Move the project to a plain path such as `C:\Users\<you>\Development\REPLIC8`, or run `npm run build` and then `npm run preview` (http://127.0.0.1:4173) instead of `npm run dev`.

## Review checks

Build with `npm run build`. Browser review covers the landing’s scroll chapters, motion preference, desktop/mobile layouts, dashboard navigation, graph inspection, operation filtering, repository-draft form, and simulated trace. Review screenshots can be regenerated under the git-ignored `web/review/` directory.
