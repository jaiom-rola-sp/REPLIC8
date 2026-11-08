# REPLIC8 architecture and deployment

Status: draft, 2026-11-07. Items marked **assumed** are recommendations the team has not confirmed. Product scope lives in [prd](prd.md); this note covers how REPLIC8 runs once deployed and what it stores.

## How a parent company uses it

A parent company gets a gateway address and a token.

- **Agents** connect to MCP at `https://<gateway>/mcp`. This is the main interface.
- **Apps** call REST at `/v1/operations/{tool}`; `/v1/openapi.json` describes the tools.
- **Admins** use the dashboard to import systems, check for changes, repair and roll back (separate admin token).

```
Parent company agents / apps
        |  HTTPS + bearer token (scoped per tool namespace)
        v
 [TLS proxy] --> [Gateway: MCP + REST + admin API] --> [Registry: versions, tests, events]
                          |
                          v
                  [Sandbox: runs legacy code, no network]
 [Dashboard] --> admin API --> [Import / repair jobs] --> GitHub (clone), Nemotron (NVIDIA API)
```

## Where it runs

The backend runs every legacy call in a Docker container, so its host must give it a Docker daemon (root-equivalent; see `docs/security.md`). Run it on a VM you control, not on serverless platforms. `deploy/` has the setup for Ubuntu 24.04 (Caddy for HTTPS, a locked-down systemd service). The frontend is a static site (Vercel) that calls the gateway directly, so the gateway lists the site's origin in `REPLIC8_CORS_ORIGINS`.

Hackathon hosting is covered in the PRD (section 8): Vultr, or a student-credit VM, with a laptop plus free tunnel as the fallback.

## What it stores, and whether it needs a database

| State | Today | Notes |
|-------|-------|-------|
| Published wrappers (versions, operations, tests, recorded cases) | JSON files under the data folder, atomic writes | Small, versioned, written on import and repair |
| Repo clones and build output | Files in the data folder | A cache: rebuilt from GitHub at the pinned commit |
| Event log | In-memory list plus `events.jsonl` | Feeds the dashboard activity |
| Tokens and scopes | Environment variables | Fail-closed scopes per namespace |
| Rate limits, running jobs | In process memory and threads | A restart drops running jobs; the registry stays consistent |

**No database is needed for one deployment on one machine**: a persistent volume plus backups is enough.

A database becomes necessary when any of these happen: more than one gateway instance (the file registry and in-process locks are not safe across instances), tokens that need issuing, expiry and revocation, a durable audit trail, jobs that must survive a restart, or several customers. At that point use **Postgres** (managed) for versions, tests, events, audit, hashed tokens and jobs, and keep clones and builds in a disk or object-storage cache. SQLite on a volume is a cheaper step for a single instance.

**SpacetimeDB is not recommended.** It is a relational database that runs application logic as modules and pushes changes to subscribed clients, aimed at games, chat and collaboration. REPLIC8's data is small and versioned, and the hard problems are sandboxed execution, authentication and hosting, none of which it solves. The agents' MCP and REST gateway is still needed. Live dashboard updates are the one fit, and polling `/v1/events` already covers them.

## The key decision for real customers: where legacy data lives

The sandbox has no network and a read-only copy of the repo, and the demo data files sit inside the repo. A real parent company's legacy systems run on live databases and files that a cloud sandbox cannot reach.

- **Cloud only** works for self-contained code or uploaded data snapshots. Limited.
- **Control plane in the cloud, runner inside the customer's network** (**assumed**): the registry, dashboard and MCP endpoint run in REPLIC8's cloud; a small runner next to the legacy data runs the sandbox and connects outbound only, so no inbound firewall holes are needed. This is roadmap, not built.

## Tenancy

**Assumed:** one deployment per customer. Each parent company gets its own server, tokens, data and model-key budget, so one customer's code and secrets can never touch another's. Shared multi-tenant hosting needs a tenants table and per-tenant isolation inside the process, and is a later phase.

## Phases

1. **Demo (now):** one VM, Docker, TLS, an image pinned by digest, a backed-up data volume, tokens in the env file, laptop plus tunnel as the fallback.
2. **First customer:** a separate deployment per customer; SQLite or Postgres; token issuing, expiry and rotation; durable audit logs; a job queue that survives restarts; rootless Docker or gVisor; the customer-network runner if they need live data.
3. **Many customers:** a shared control plane with a tenants table; workers scaled separately for imports, repairs and calls; Postgres plus Redis for rate limits; object storage for the repo and build cache.
