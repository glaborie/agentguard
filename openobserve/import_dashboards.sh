#!/usr/bin/env bash
# Import AgentGuard dashboards into OpenObserve.
# Usage: ./openobserve/import_dashboards.sh
# Requires: ZO_ROOT_USER_EMAIL, ZO_ROOT_USER_PASSWORD in env (or .env loaded).

set -euo pipefail

: "${ZO_ROOT_USER_EMAIL:=root@example.com}"
: "${ZO_ROOT_USER_PASSWORD:=Complexpass#123}"
OPENOBSERVE_URL="${OPENOBSERVE_URL:-http://localhost:5080}"
ORG="${ZO_ORG:-default}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARDS_DIR="$SCRIPT_DIR/dashboards"

echo "Importing dashboards → $OPENOBSERVE_URL (org: $ORG)"

for f in "$DASHBOARDS_DIR"/*.json; do
  name=$(basename "$f" .json)
  echo -n "  $name ... "
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST \
    -u "${ZO_ROOT_USER_EMAIL}:${ZO_ROOT_USER_PASSWORD}" \
    -H "Content-Type: application/json" \
    -d @"$f" \
    "${OPENOBSERVE_URL}/api/${ORG}/dashboards")
  if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    echo "OK ($HTTP_CODE)"
  else
    echo "FAIL ($HTTP_CODE)"
    exit 1
  fi
done

echo "Done. Open $OPENOBSERVE_URL and go to Dashboards."
