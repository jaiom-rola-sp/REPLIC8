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

The default workspace is an explicitly labeled demo. Its graph, operations, source locations, event stream, metrics, and trace are illustrative. You can inspect graph nodes, pan/zoom, filter systems and tools, save/remove session-only repository drafts, and run a simulated request through two systems. No code is cloned or executed and no messages are sent by these interactions.

Gateway settings can load real health and operation-registry data from an existing backend. The default `/gateway` address uses Vite’s development proxy to `http://127.0.0.1:8000`. To use another backend target:

```sh
REPLIC8_GATEWAY_URL=http://127.0.0.1:9000 npm run dev
```

Enter the gateway bearer token in the app’s Settings dialog. It is kept in browser session storage, never in source files or build variables. The connected registry uses only `GET /health` and `GET /v1/operations`; graph edges then represent gateway registration, not cross-system data flows.

The backend currently has no graph/event-stream, ingest, repair, or history HTTP endpoints, so these are not represented as live integrations. Direct HTTP(S) gateway addresses require the backend to allow the browser’s origin. A production deployment needs a same-origin gateway proxy or deliberate CORS configuration; Vite’s development proxy is not part of `dist/`.

## Review checks

Build with `npm run build`. Browser review covers the landing’s scroll chapters, motion preference, desktop/mobile layouts, dashboard navigation, graph inspection, operation filtering, repository-draft form, and simulated trace. Review screenshots can be regenerated under the git-ignored `web/review/` directory.
