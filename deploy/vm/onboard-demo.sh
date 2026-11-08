#!/usr/bin/env bash
# Onboard the two demo legacy systems on the server and wait until both are published.
#   sudo bash /opt/replic8/deploy/vm/onboard-demo.sh
# Reads the admin token from /etc/replic8/replic8.env; it is never printed.
set -euo pipefail

ENV_FILE=/etc/replic8/replic8.env
BASE="${REPLIC8_URL:-http://127.0.0.1:8000}"

admin="$(sed -n 's/^REPLIC8_ADMIN_TOKENS=\([^,]*\).*/\1/p' "$ENV_FILE")"
gateway="$(sed -n 's/^REPLIC8_GATEWAY_TOKENS=\([^,]*\).*/\1/p' "$ENV_FILE")"
if [[ -z "$admin" || -z "$gateway" ]]; then echo "Tokens missing in $ENV_FILE" >&2; exit 1; fi

onboard() {
  curl -fsS -X POST "$BASE/v1/admin/systems" \
    -H "Authorization: Bearer $admin" -H "Content-Type: application/json" -d "$1" >/dev/null
}

onboard '{"system":"maintenance","repo_url":"local://b-maintenance-cobol","examples":{"get_request":[{"request_id":"R-1001"}],"list_open_requests":[{"well_id":"W-17"}],"list_site_requests":[{"site":"PERMIAN"}],"get_well":[{"well_id":"W-44"}],"get_service_history":[{"well_id":"W-44"}],"get_technician":[{"tech_id":"T-101"}],"find_available_techs":[{"site":"PERMIAN","skill":"ELECTRICAL"}],"calc_downtime_cost":[{"well_id":"W-44","days":7}],"get_well_risk":[{"well_id":"W-44"}]}}'
onboard '{"system":"inventory","repo_url":"local://c-inventory-java","examples":{"check_stock":[{"part_id":"PMP-2210"}],"get_shipping_options":[{"part_id":"PMP-2210","destination":"PERMIAN"}],"get_warehouse":[{"warehouse":"ODESSA"}],"list_low_stock":[{"warehouse":"ODESSA"}],"get_supplier":[{"supplier_id":"SUP-030"}],"get_part_sourcing":[{"part_id":"CBL-0500"}],"list_purchase_orders":[{"part_id":"CBL-0500"}],"get_cheapest_shipping":[{"part_id":"CBL-0500","destination":"PERMIAN"}],"quote_delivery":[{"part_id":"CBL-0500","destination":"PERMIAN","quantity":2}]}}'
echo "Onboarding started. Waiting for both systems (about 10 to 60 seconds)..."

for _ in $(seq 1 60); do
  done_count="$(curl -fsS "$BASE/v1/events" -H "Authorization: Bearer $gateway" |
    python3 -c 'import json,sys; print(sum(e["kind"] in ("published","onboard_failed") for e in json.load(sys.stdin)["events"]))')"
  [[ "$done_count" -ge 2 ]] && break
  sleep 3
done

curl -fsS "$BASE/v1/events" -H "Authorization: Bearer $gateway" | python3 -c '
import json, sys
for e in json.load(sys.stdin)["events"]:
    if e["kind"] in ("published", "onboard_failed", "contract_failed", "schema_adjusted"):
        print("  %-16s %-12s %s %s" % (e["kind"], e["system"], e.get("tool", ""), e.get("detail", "")))'
curl -fsS "$BASE/v1/operations" -H "Authorization: Bearer $gateway" |
  python3 -c 'import json,sys; [print("  tool:", o["tool"], o["source"]) for o in json.load(sys.stdin)["operations"]]'
