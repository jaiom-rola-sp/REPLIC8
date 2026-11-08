#!/usr/bin/env bash
# REPLIC8 backend setup for a fresh Ubuntu 24.04 server (Azure VM). Run as root.
#
#   sudo REPLIC8_DOMAIN=replic8-demo.eastus.cloudapp.azure.com bash deploy/vm/setup.sh
#
# Safe to re-run. It installs Docker, Caddy (HTTPS) and Python, creates a
# `replic8` service user, installs the backend into /opt/replic8, builds the
# legacy runtime image, and starts two services: replic8 (127.0.0.1:8000) and
# Caddy (ports 80/443, automatic HTTPS). Secrets live in /etc/replic8/replic8.env,
# which this script creates from the example once and never overwrites.
set -euo pipefail

DOMAIN="${REPLIC8_DOMAIN:-}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_DIR=/opt/replic8
DATA_DIR=/var/lib/replic8
ENV_FILE=/etc/replic8/replic8.env

if [[ $EUID -ne 0 ]]; then echo "Run as root (sudo)." >&2; exit 1; fi
if [[ -z "$DOMAIN" ]]; then
  echo "Set REPLIC8_DOMAIN to the backend's hostname, e.g. api.example.com or <ip-with-dashes>.sslip.io" >&2
  exit 1
fi
if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]]; then echo "REPLIC8_DOMAIN has invalid characters." >&2; exit 1; fi

echo "== Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q docker.io caddy python3-venv git ufw unattended-upgrades
systemctl enable --now docker

echo "== Service user and folders"
id replic8 >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin replic8
# The backend starts sandbox containers, so it needs Docker. Docker access is
# root-equivalent (docs/security.md), which is why this server should run nothing else.
usermod -aG docker replic8
install -d -o replic8 -g replic8 -m 0750 "$DATA_DIR"
install -d -o root -g replic8 -m 0750 /etc/replic8

echo "== Code"
# Copy the checkout (without local caches) to a root-owned, read-only location.
mkdir -p "$APP_DIR"
tar -C "$REPO_DIR" --exclude=.git --exclude=node_modules --exclude=graphify-out --exclude=__pycache__ \
    --exclude='backend/data' --exclude='web/dist' -cf - . | tar -C "$APP_DIR" -xf -
chown -R root:root "$APP_DIR"
chmod -R go-w "$APP_DIR"

echo "== Python environment"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q "$APP_DIR/backend"

echo "== Parser grammars (downloaded once, so the service never fetches code at runtime)"
install -d -o replic8 -g replic8 -m 0700 "$DATA_DIR/grammars"
runuser -u replic8 -- env TREE_SITTER_LANGUAGE_PACK_CACHE_DIR="$DATA_DIR/grammars" \
  "$APP_DIR/venv/bin/python" -c 'import tree_sitter_language_pack as t; from replic8.extract import EXTRACTORS; t.download(sorted(EXTRACTORS))'

echo "== Legacy runtime image (COBOL, Fortran, Java, C, Pascal, Python, Perl, PHP)"
docker build -q -t replic8-legacy-runtime:1 "$APP_DIR/backend/runtime"

echo "== Secrets file"
if [[ ! -f "$ENV_FILE" ]]; then
  install -o root -g replic8 -m 0640 "$APP_DIR/deploy/vm/replic8.env.example" "$ENV_FILE"
  gateway="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
  admin="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
  # Gateway tokens are fail-closed: give this one the two demo systems.
  gateway_id="$(printf '%s' "$gateway" | sha256sum | cut -c1-12)"
  sed -i "s|^REPLIC8_GATEWAY_TOKENS=.*|REPLIC8_GATEWAY_TOKENS=$gateway|; s|^REPLIC8_ADMIN_TOKENS=.*|REPLIC8_ADMIN_TOKENS=$admin|; s|^REPLIC8_TOKEN_SCOPES=.*|REPLIC8_TOKEN_SCOPES=$gateway_id=maintenance.*\|inventory.*|; s|^REPLIC8_ALLOWED_HOSTS=.*|REPLIC8_ALLOWED_HOSTS=$DOMAIN,127.0.0.1:*,localhost:*|" "$ENV_FILE"
  echo "   Created $ENV_FILE with new random tokens. Add NVIDIA_API_KEY and REPLIC8_CORS_ORIGINS next."
else
  echo "   Keeping existing $ENV_FILE"
fi
# Pin the sandbox to the exact image just built (rebuilt images get a new digest).
pinned="$(docker image inspect replic8-legacy-runtime:1 --format '{{.Id}}')"
if [[ ! "$pinned" =~ ^sha256:[0-9a-f]{64}$ ]]; then echo "Could not read the runtime image digest." >&2; exit 1; fi
sed -i "s|^REPLIC8_SANDBOX_IMAGES=.*|REPLIC8_SANDBOX_IMAGES=replic8-legacy-runtime:1@$pinned|" "$ENV_FILE"
echo "   Sandbox image pinned: replic8-legacy-runtime:1@${pinned:0:19}..."

echo "== Services"
install -m 0644 "$APP_DIR/deploy/vm/replic8.service" /etc/systemd/system/replic8.service
sed "s|{\$REPLIC8_DOMAIN}|$DOMAIN|" "$APP_DIR/deploy/vm/Caddyfile" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl daemon-reload
systemctl enable replic8
systemctl restart replic8
systemctl reload-or-restart caddy

echo "== Firewall: only SSH, HTTP and HTTPS"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo
echo "Done. Next:"
echo "  1. Edit $ENV_FILE: set NVIDIA_API_KEY and REPLIC8_CORS_ORIGINS (your Vercel URL)."
echo "  2. systemctl restart replic8"
echo "  3. curl https://$DOMAIN/health"
echo "  4. sudo bash $APP_DIR/deploy/vm/onboard-demo.sh"
