#!/usr/bin/env bash
# Deploy new code to the server from a fresh checkout. Run as root from the checkout:
#   cd ~/REPLIC8 && git pull && sudo REPLIC8_DOMAIN=replic8-demo.eastus.cloudapp.azure.com bash deploy/vm/update.sh
# Same steps as setup.sh (it is safe to re-run); secrets and data are kept.
set -euo pipefail
exec bash "$(dirname "${BASH_SOURCE[0]}")/setup.sh"
