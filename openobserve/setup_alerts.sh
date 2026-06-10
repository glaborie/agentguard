#!/usr/bin/env bash
# Create AgentGuard observability alerts in OpenObserve (v2 API).
# Requires: ALERT_WEBHOOK_URL in env (or .env loaded).
# Optional overrides: ZO_ROOT_USER_EMAIL, ZO_ROOT_USER_PASSWORD, OPENOBSERVE_URL
#
# Usage:
#   ALERT_WEBHOOK_URL=https://hooks.slack.com/services/xxx ./openobserve/setup_alerts.sh
#   # Or set in .env and source it first.

set -euo pipefail

: "${ZO_ROOT_USER_EMAIL:=root@example.com}"
: "${ZO_ROOT_USER_PASSWORD:=Complexpass#123}"
: "${OPENOBSERVE_URL:=http://localhost:5080}"
: "${ZO_ORG:=default}"
: "${ALERT_WEBHOOK_URL:=}"

BASE="$OPENOBSERVE_URL/api"
AUTH="-u ${ZO_ROOT_USER_EMAIL}:${ZO_ROOT_USER_PASSWORD}"

_post() {
  local path="$1"; shift
  local data="$1"; shift
  local code
  code=$(curl -s -o /tmp/oo_alert_resp.json -w "%{http_code}" \
    $AUTH -X POST -H "Content-Type: application/json" \
    -d "$data" "$BASE/$path" 2>/dev/null)
  local body; body=$(cat /tmp/oo_alert_resp.json)
  if [ "$code" -ge 200 ] && [ "$code" -lt 300 ]; then
    echo "OK ($code)"
  else
    echo "FAIL ($code): $body"
    return 1
  fi
}

_put() {
  local path="$1"; shift
  local data="$1"; shift
  local code
  code=$(curl -s -o /tmp/oo_alert_resp.json -w "%{http_code}" \
    $AUTH -X PUT -H "Content-Type: application/json" \
    -d "$data" "$BASE/$path" 2>/dev/null)
  local body; body=$(cat /tmp/oo_alert_resp.json)
  if [ "$code" -ge 200 ] && [ "$code" -lt 300 ]; then
    echo "OK ($code)"
  else
    echo "FAIL ($code): $body"
    return 1
  fi
}

echo "=== AgentGuard OpenObserve Alert Setup ==="
echo "Target: $OPENOBSERVE_URL (org: $ZO_ORG)"

# OO v2 ?overwrite=true creates duplicates instead of replacing by name.
# Delete all existing AgentGuard alerts first so re-runs stay idempotent.
echo -n "[0/6] Deleting existing agentguard alerts ... "
EXISTING=$(curl -s $AUTH "$BASE/v2/$ZO_ORG/alerts" 2>/dev/null)
echo "$EXISTING" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for a in d.get('list',[]):
    if a['name'].startswith('agentguard-'):
        print(a['alert_id'])
" 2>/dev/null | while read -r aid; do
  curl -s $AUTH -X DELETE "$BASE/v2/$ZO_ORG/alerts/$aid" >/dev/null 2>&1
done
echo "done"

# ── 1. Template ──────────────────────────────────────────────────────────────
echo -n "[1/6] Upserting alert template ... "
_put "$ZO_ORG/alerts/templates/agentguard-webhook" '{
  "name": "agentguard-webhook",
  "body": "{\"alert\": \"{alert_name}\", \"org\": \"{org_name}\", \"stream\": \"{stream_name}\", \"condition\": \"{alert_operator} {alert_threshold}\", \"value\": \"{alert_value}\", \"start\": \"{alert_start_time}\", \"url\": \"{alert_url}\"}",
  "type": "http"
}'

# ── 2. Destination ────────────────────────────────────────────────────────────
if [ -z "$ALERT_WEBHOOK_URL" ]; then
  echo ""
  echo "WARNING: ALERT_WEBHOOK_URL not set. Creating destination with placeholder URL."
  echo "         Update it in OpenObserve UI: Alerts → Destinations → agentguard-webhook"
  ALERT_WEBHOOK_URL="https://example.com/webhook-placeholder"
fi

echo -n "[2/6] Upserting webhook destination ... "
# Try PUT (update existing) first; fall back to POST (create new).
_put "$ZO_ORG/alerts/destinations/agentguard-webhook" "{
  \"name\": \"agentguard-webhook\",
  \"url\": \"$ALERT_WEBHOOK_URL\",
  \"method\": \"post\",
  \"skip_tls_verify\": false,
  \"headers\": {\"Content-Type\": \"application/json\"},
  \"template\": \"agentguard-webhook\",
  \"type\": \"http\"
}" || _post "$ZO_ORG/alerts/destinations" "{
  \"name\": \"agentguard-webhook\",
  \"url\": \"$ALERT_WEBHOOK_URL\",
  \"method\": \"post\",
  \"skip_tls_verify\": false,
  \"headers\": {\"Content-Type\": \"application/json\"},
  \"template\": \"agentguard-webhook\",
  \"type\": \"http\"
}"

# ── 3. Alert: Error rate spike ────────────────────────────────────────────────
# Fires when ≥5 ERROR spans appear within a 5-minute window, checked every 5 min.
echo -n "[3/6] Creating alert: error-rate-spike ... "
_post "v2/$ZO_ORG/alerts" '{
  "name": "agentguard-error-rate-spike",
  "stream_type": "traces",
  "stream_name": "default",
  "is_real_time": false,
  "query_condition": {
    "type": "sql",
    "sql": "SELECT count(*) AS error_count FROM \"default\" WHERE status_code = 2",
    "conditions": null,
    "promql": null,
    "promql_condition": null,
    "aggregation": {
      "group_by": [],
      "function": "count",
      "having": {
        "column": "error_count",
        "operator": ">=",
        "value": 5
      }
    },
    "vrl_function": null,
    "search_event_type": "alerts",
    "multi_time_range": []
  },
  "trigger_condition": {
    "period": 5,
    "operator": ">=",
    "threshold": 1,
    "frequency": 5,
    "frequency_type": "minutes",
    "silence": 30,
    "timezone": "UTC",
    "tolerance_in_secs": null
  },
  "destinations": ["agentguard-webhook"],
  "context_attributes": {},
  "row_template": "",
  "description": "Fires when >=5 ERROR spans appear in a 5-minute window. Indicates service failures.",
  "enabled": true,
  "tz_offset": 0
}'

# ── 4. Alert: High LLM latency ────────────────────────────────────────────────
# Fires when avg ChatOpenAI duration exceeds 30s (30_000_000 µs) in 10-min window.
echo -n "[4/6] Creating alert: high-llm-latency ... "
_post "v2/$ZO_ORG/alerts" '{
  "name": "agentguard-high-llm-latency",
  "stream_type": "traces",
  "stream_name": "default",
  "is_real_time": false,
  "query_condition": {
    "type": "sql",
    "sql": "SELECT avg(duration) AS avg_duration_us FROM \"default\" WHERE operation_name = '\''ChatOpenAI'\''",
    "conditions": null,
    "promql": null,
    "promql_condition": null,
    "aggregation": {
      "group_by": [],
      "function": "avg",
      "having": {
        "column": "avg_duration_us",
        "operator": ">=",
        "value": 30000000
      }
    },
    "vrl_function": null,
    "search_event_type": "alerts",
    "multi_time_range": []
  },
  "trigger_condition": {
    "period": 10,
    "operator": ">=",
    "threshold": 1,
    "frequency": 10,
    "frequency_type": "minutes",
    "silence": 60,
    "timezone": "UTC",
    "tolerance_in_secs": null
  },
  "destinations": ["agentguard-webhook"],
  "context_attributes": {},
  "row_template": "",
  "description": "Fires when avg LLM latency exceeds 30s over 10 minutes. Threshold: 30000000 µs.",
  "enabled": true,
  "tz_offset": 0
}'

# ── 5. Alert: Guardrail block spike ───────────────────────────────────────────
# Fires when >=3 RunnableSequence spans end in ERROR within 5 min (proxy returning 400/403
# causes the chain span to fail — no dedicated guardrail span in OTel traces).
echo -n "[5/6] Creating alert: guardrail-block-spike ... "
_post "v2/$ZO_ORG/alerts" '{
  "name": "agentguard-guardrail-block-spike",
  "stream_type": "traces",
  "stream_name": "default",
  "is_real_time": false,
  "query_condition": {
    "type": "sql",
    "sql": "SELECT count(*) AS blocked FROM \"default\" WHERE operation_name = '\''RunnableSequence'\'' AND status_code = 2",
    "conditions": null,
    "promql": null,
    "promql_condition": null,
    "aggregation": {
      "group_by": [],
      "function": "count",
      "having": {
        "column": "blocked",
        "operator": ">=",
        "value": 3
      }
    },
    "vrl_function": null,
    "search_event_type": "alerts",
    "multi_time_range": []
  },
  "trigger_condition": {
    "period": 5,
    "operator": ">=",
    "threshold": 1,
    "frequency": 5,
    "frequency_type": "minutes",
    "silence": 30,
    "timezone": "UTC",
    "tolerance_in_secs": null
  },
  "destinations": ["agentguard-webhook"],
  "context_attributes": {},
  "row_template": "",
  "description": "Fires when >=3 RAG chain requests fail in 5 min — indicates guardrail blocking spike or attack.",
  "enabled": true,
  "tz_offset": 0
}'


# ── 6. Alert: Guardrail block in logs (log-based, catches all guard types) ────
# score_guardrail_block() logs WARNING "guardrail block | type=..." via Docker logs
# → Promtail → OO logs stream. Fires on first block (threshold=1) — real-time signal.
echo -n "[6/6] Creating alert: guardrail-block-log ... "
_post "v2/$ZO_ORG/alerts" '{
  "name": "agentguard-guardrail-block-log",
  "stream_type": "logs",
  "stream_name": "default",
  "is_real_time": false,
  "query_condition": {
    "type": "sql",
    "sql": "SELECT count(*) AS block_count FROM \"default\" WHERE message LIKE '\''%guardrail block%'\''",
    "conditions": null,
    "promql": null,
    "promql_condition": null,
    "aggregation": {
      "group_by": [],
      "function": "count",
      "having": {
        "column": "block_count",
        "operator": ">=",
        "value": 1
      }
    },
    "vrl_function": null,
    "search_event_type": "alerts",
    "multi_time_range": []
  },
  "trigger_condition": {
    "period": 5,
    "operator": ">=",
    "threshold": 1,
    "frequency": 2,
    "frequency_type": "minutes",
    "silence": 10,
    "timezone": "UTC",
    "tolerance_in_secs": null
  },
  "destinations": ["agentguard-webhook"],
  "context_attributes": {},
  "row_template": "",
  "description": "Fires when any guardrail block appears in app logs within 5 min. Log-based — catches prompt injection, toxicity, and semantic guard blocks regardless of OTel span presence.",
  "enabled": true,
  "tz_offset": 0
}'

echo ""
echo "=== Done ==="
echo "View alerts: $OPENOBSERVE_URL → Alerts"
if [[ "$ALERT_WEBHOOK_URL" == *"placeholder"* ]]; then
  echo ""
  echo "Next: set ALERT_WEBHOOK_URL and re-run, or update destination in UI."
  echo "  Slack:   https://hooks.slack.com/services/..."
  echo "  Discord: https://discord.com/api/webhooks/..."
  echo "  Custom:  any POST endpoint accepting JSON"
fi
