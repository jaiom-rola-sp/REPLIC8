# Deploying REPLIC8

| Part | Where | Who |
|------|-------|-----|
| Frontend (`web/`) | Vercel | Jai |
| Backend (`backend/`): MCP + REST gateway, sandbox, Nemotron | One Vultr server | Backend team |

The browser talks to the backend over HTTPS. AI agents talk to the same backend over MCP at `https://<backend domain>/mcp`.

## 1. Create the Vultr server

1. In Vultr, **Deploy New Server**, then choose **Cloud Compute**, **Ubuntu 24.04 LTS x64**, and at least **2 vCPU / 4 GB RAM** (compiling COBOL and Java runs on this machine). Pick a region near the demo.
2. Add your **SSH key**. Don't use password login.
3. Optional but recommended: a **Vultr Firewall Group** allowing only TCP 22, 80 and 443. `setup.sh` also turns on the same rules with `ufw`.
4. Note the server's public IPv4 address.

## 2. Pick the backend's hostname

HTTPS needs a hostname, because the Vercel site is HTTPS and browsers block calls to plain HTTP.

- **Own domain:** add a DNS `A` record such as `api.yourdomain.com` pointing at the server IP.
- **No domain:** use `<ip-with-dashes>.sslip.io`. For example, IP `203.0.113.7` becomes `203-0-113-7.sslip.io`, which resolves to that IP with no DNS setup.

Caddy gets the HTTPS certificate automatically on first start.

## 3. Install the backend

SSH in, get the code onto the server, and run the setup script:

```bash
ssh root@<server ip>
```

```bash
git clone https://github.com/jaiom-rola-sp/REPLIC8.git && cd REPLIC8
```

If the repo is private, clone with a read-only GitHub fine-grained token, or copy it up with `scp`.

```bash
sudo REPLIC8_DOMAIN=<your hostname> bash deploy/vultr/setup.sh
```

The script installs Docker, Caddy and Python, creates a `replic8` service user, installs the backend in `/opt/replic8`, pre-downloads the COBOL/Java/Fortran parser grammars, builds the legacy runtime image and pins the sandbox to its exact digest, writes `/etc/replic8/replic8.env` with fresh random tokens (the gateway token is scoped to `maintenance.*` and `inventory.*`), and starts the `replic8` and `caddy` services. It takes about 5 to 10 minutes the first time.

## 4. Add the secrets

```bash
sudo nano /etc/replic8/replic8.env
```

Set:

- `NVIDIA_API_KEY`: the Nemotron key.
- `REPLIC8_CORS_ORIGINS`: the Vercel site's exact address, e.g. `https://replic8.vercel.app`. Several are comma-separated. No trailing slash, no `*`.

Then restart and check:

```bash
sudo systemctl restart replic8
```

```bash
curl https://<your hostname>/health
```

That should print `{"status":"ok"}`.

## 5. Load the demo systems

```bash
sudo bash /opt/replic8/deploy/vultr/onboard-demo.sh
```

It onboards Company B (COBOL) and Company C (Java) and prints the four published tools.

## 6. Hand-offs

- **To Jai (Vercel):** the gateway address `https://<your hostname>` and the **gateway** token (`REPLIC8_GATEWAY_TOKENS` in the env file). The token is typed into the dashboard's Settings dialog. Never put it in the frontend code or a Vercel environment variable.
- **To the demo agent:** the MCP URL `https://<your hostname>/mcp` and the gateway token.
- **Keep the admin token** (`REPLIC8_ADMIN_TOKENS`) on the server only.
- **New systems need scopes.** Gateway tokens are fail-closed: after onboarding a new system, add `<namespace>.*` to the token's entry in `REPLIC8_TOKEN_SCOPES` and restart, or the dashboard and agents won't see its tools.

To read a token on the server:

```bash
sudo grep TOKENS /etc/replic8/replic8.env
```

## Day-to-day

| Task | Command |
|------|---------|
| Logs | `sudo journalctl -u replic8 -f` |
| Restart | `sudo systemctl restart replic8` |
| Deploy new code | `cd ~/REPLIC8 && git pull && sudo REPLIC8_DOMAIN=<hostname> bash deploy/vultr/update.sh` |
| Live self-heal demo | Edit `/opt/replic8/legacy/b-maintenance-cobol/src/MAINT.cbl` (rename `GET-REQUEST` to `FETCH-REQUEST` in both places), then `POST /v1/admin/systems/maintenance/check` with the admin token |
| Undo the demo rename | Re-run `update.sh` (it copies the repo's code back) |

## What the setup protects

- Only Caddy listens publicly (80/443). The app listens on `127.0.0.1:8000`.
- The service runs as `replic8`, not root, with systemd hardening; its only writable folder is `/var/lib/replic8`. The code in `/opt/replic8` is root-owned and read-only.
- Secrets live only in `/etc/replic8/replic8.env` (`root:replic8`, mode 0640).
- The parser grammars are downloaded during setup, so the running service never fetches code.
- The `replic8` user is in the `docker` group, which is root-equivalent. Run nothing else on this server (see `docs/security.md`).

## Rehearsal

On 2026-11-08 the install was rehearsed in the development container: a separate non-root service user in the docker group, a venv installed from a repo copy, pre-downloaded grammars, settings from an env file, then health, CORS (Vercel origin allowed, other origins refused), MCP with the server's hostname, onboarding of both systems, and the MCP demo. systemd, Caddy's certificate and the firewall could not be exercised there; `caddy validate` and `shellcheck` pass.
