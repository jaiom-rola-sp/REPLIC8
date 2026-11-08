# Deploying REPLIC8

| Part | Where | Who |
|------|-------|-----|
| Frontend (`web/`) | Vercel, live at https://www.replic8.work | Jai |
| Backend (`backend/`): MCP + REST gateway, sandbox, Nemotron | One Azure VM (Azure for Students) | Backend team |

The browser talks to the backend over HTTPS. AI agents talk to the same backend over MCP at `https://<backend hostname>/mcp`.

## 1. Create the Azure VM

Azure for Students gives credit without a card. In the [Azure portal](https://portal.azure.com):

1. **Create a resource**, then **Virtual machine**.
2. **Basics:**
   - Resource group: new, e.g. `replic8-rg`. Region: one near the demo that your student subscription allows (if a size is unavailable, try another region).
   - Image: **Ubuntu Server 24.04 LTS - x64 Gen2**.
   - Size: **Standard_B2s** (2 vCPU, 4 GB RAM). Compiling COBOL and Java runs on this machine, so don't go smaller.
   - Authentication: **SSH public key**, username `azureuser`. Download the key Azure generates (or paste your own).
   - Inbound ports: allow **SSH (22)**, **HTTP (80)** and **HTTPS (443)**.
3. **Disks:** the default 30 GB is enough.
4. **Review + create**, then **Create**.
5. When it's deployed, open the VM. Under **Networking**, edit the SSH (22) rule's **Source** to *My IP address*, so only you can SSH in. Leave 80 and 443 open to the internet.
6. **Stop the VM when you're not using it** (Overview, **Stop**) so it doesn't use up the student credit. The public IP and hostname stay the same if you set the IP to **Static** under Networking, then the public IP.

## 2. Give it a hostname (free)

HTTPS needs a hostname, because the Vercel site is HTTPS and browsers block calls to plain HTTP. Azure gives one for free:

1. Open the VM, then click its **Public IP address**, then **Configuration**.
2. Set **DNS name label** to something like `replic8-demo`, and **Save**.
3. Your hostname is now `replic8-demo.<region>.cloudapp.azure.com` (shown on that page as the DNS name).

Caddy gets the HTTPS certificate for it automatically on first start. With your own domain instead, add a DNS `CNAME` record pointing at that Azure hostname.

## 3. Install the backend

SSH in, get the code onto the server, and run the setup script:

```bash
ssh -i <path to the downloaded key>.pem azureuser@<your hostname>
```

```bash
git clone https://github.com/jaiom-rola-sp/REPLIC8.git && cd REPLIC8
```

If the repo is private, clone with a read-only GitHub fine-grained token, or copy it up with `scp`. On Windows, `ssh` works in PowerShell; if it complains about key permissions, right-click the `.pem` file, **Properties**, **Security**, and leave only your own user with access.

```bash
sudo REPLIC8_DOMAIN=<your hostname> bash deploy/vm/setup.sh
```

The script installs Docker, Caddy and Python, creates a `replic8` service user, installs the backend in `/opt/replic8`, pre-downloads the COBOL/Java/Fortran parser grammars, builds the legacy runtime image and pins the sandbox to its exact digest, writes `/etc/replic8/replic8.env` with fresh random tokens (the gateway token is scoped to `maintenance.*` and `inventory.*`), and starts the `replic8` and `caddy` services. It takes about 5 to 10 minutes the first time.

## 4. Add the secrets

```bash
sudo nano /etc/replic8/replic8.env
```

Set:

- `NVIDIA_API_KEY`: the Nemotron key.
- `REPLIC8_CORS_ORIGINS`: the Vercel site's exact address, `https://www.replic8.work`. Several are comma-separated (add `https://replic8.work` too if the bare domain does not redirect to www). No trailing slash, no `*`.

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
sudo bash /opt/replic8/deploy/vm/onboard-demo.sh
```

It onboards Company B (COBOL) and Company C (Java) and prints the four published tools.

## 6. Hand-offs

- **To Jai (Vercel):** the gateway address `https://<your hostname>` and the **gateway** token (`REPLIC8_GATEWAY_TOKENS` in the env file). The token is typed into the dashboard's Settings dialog. Never put it in the frontend code or a Vercel environment variable. To have the dashboard start with the gateway address filled in, set `VITE_REPLIC8_GATEWAY=https://<your hostname>` in Vercel (Project, Settings, Environment Variables) and redeploy. That is the address only, never a token (see `web/.env.example`).
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
| Deploy new code | `cd ~/REPLIC8 && git pull && sudo REPLIC8_DOMAIN=<hostname> bash deploy/vm/update.sh` |
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

## Fallback: laptop plus a free tunnel

If the VM isn't available on demo day, run REPLIC8 on a laptop (see `backend/README.md` and `readme.md`) and publish it with a free Cloudflare quick tunnel. No account is needed.

1. Start the backend on the laptop as usual (it listens on `127.0.0.1:8000`).
2. Install `cloudflared` (Windows: `winget install --id Cloudflare.cloudflared`) and run:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

3. It prints an address like `https://<random-words>.trycloudflare.com`. Restart the backend with that hostname added to `REPLIC8_ALLOWED_HOSTS` (for MCP) and the Vercel address in `REPLIC8_CORS_ORIGINS`.
4. In the dashboard's Settings, use the tunnel address as the gateway address. Agents use `<tunnel address>/mcp`.

The address changes every time the tunnel starts, and anyone with it can reach the gateway's login, so use fresh tokens and stop the tunnel after the demo (`docs/security.md`).
