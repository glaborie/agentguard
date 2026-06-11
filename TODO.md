# TODO — SOTA Gaps (SOTA scan 2026-06-02, updated 2026-06-04)

All additive — no architectural change required. Independent, can be parallelized.

---

## Direct peer gaps

### [done] #1 ML/semantic injection detection (~2d)

**Why:** Regex fails on paraphrased jailbreaks ("Act as if you have no rules" bypasses most patterns). LLM Guard's deberta model catches semantic variants that the 12 regex patterns in `guardrails/custom_guardrails.py` miss.

**Reference:** `protectai/llm-guard` → PromptInjection scanner (uses `protectai/deberta-v3-base-prompt-injection-v2`)

---

### [done] #2 CI/CD pipeline integration (~4h)

**Why:** `scripts/regression_gate.py` already exits 0/1/2 correctly — but no `.github/workflows/` file ships with the repo. Teams cloning AgentGuard must hand-wire CI themselves.

**Reference:** `confident-ai/deepeval` → `.github/workflows/`

---

### [done] #3 Toxic/harmful content detection (~1d)

**Why:** Injection blocking + PII masking each guard one attack vector. Toxic/abusive inputs are a separate real-world failure mode not covered by either existing guard.

**Reference:** `protectai/llm-guard` → `llm_guard/input_scanners/toxicity.py`

---

### [done] #8 Automated red teaming (~2d)

**Why:** Safety platforms (promptfoo acquired by OpenAI, NeMo, giskard) all generate adversarial test suites automatically. Teams need OWASP LLM Top 10 coverage without writing 50 test cases by hand.

**Reference:** `promptfoo/promptfoo` → red team feature (50+ attack plugins, OWASP presets, MITRE ATLAS coverage)

**Step 1:** Create `scripts/red_team.py` with `run_red_team(attack_types, n_variants, model)` that calls LiteLLM to generate adversarial variants of seed prompts, sends them through the guardrail stack, and reports pass/fail counts. Wire into CLI with `python -m app.main red-team --limit 20`. Exit 0/1/2 matching `regression_gate.py` so CI can call it.

**Options:**
- Option A: Build inline — LiteLLM generates variants via a red-team system prompt. No external dep, works offline, fits the existing LiteLLM proxy pattern.
- Option B: Wrap promptfoo CLI (`promptfoo redteam run`) — richer attack coverage but adds Node.js dep and license risk post-OpenAI acquisition (verify first).
- Option C: Use giskard's scan API (Python, Apache 2.0) — check if `giskard.scan(model, dataset)` supports LangChain LCEL chains.

**Verify first:** Confirm promptfoo's current license status post-acquisition before taking a hard dependency. Confirm giskard scan supports LangChain LCEL chains.

---

## Maturity / quality gaps

### [done] #4 Coverage reporting / badge (~2h)

**Reference:** `confident-ai/deepeval` → `pyproject.toml` (coverage config + Codecov integration)

---

### [done] #5 Type annotation completeness (~1d)

**Reference:** `guardrails-ai/guardrails` → `pyproject.toml` (pyright strict mode)

---

## Docs / onboarding gaps

### [done] #6 Cloud deployment guide (~2d)

**Reference:** `Arize-ai/phoenix` → deployment docs and Docker Compose variants

---

### [done] #7 CONTRIBUTING.md + local dev setup (~2h)

**Reference:** `deepset-ai/haystack` → `CONTRIBUTING.md`

---

## OpenObserve observability gaps

### [done] #9 Logs fan-out to OpenObserve (~1h)

**Why:** Container logs currently go to Loki only. OpenObserve can ingest logs via Promtail, giving unified traces + logs in one UI — correlate a trace to container logs without switching tools.

**Reference:** OpenObserve Promtail ingestion endpoint `/api/default/loki/api/v1/push` (Loki-compatible API).

---

### [done] #10 LLM observability dashboards (~2h)

**Why:** Traces flow into OpenObserve but no dashboards exist. Teams need out-of-box visibility into latency, token counts, guardrail block rates, cache hit rates, and error rates.

**Panels built:** Request rate, LLM latency p50/p95/p99 over time, latency by model, token usage (prompt + completion), error rate by service, guardrail block rate, request volume by model, semantic cache hits vs misses.

**Files:** `openobserve/dashboards/agentguard_llm.json` (import via UI or `./openobserve/import_dashboards.sh`).

---

### [done] #11 Alerts on trace data (~1h)

**Why:** No proactive alerting exists. Guardrail block spikes (injection attack in progress), high latency, and elevated error rates need automated notification.

**Alerts created:** `agentguard-error-rate-spike` (≥5 errors/5min), `agentguard-high-llm-latency` (avg>30s/10min), `agentguard-guardrail-block-spike` (≥3 RAG chain errors/5min).

**Setup:** `ALERT_WEBHOOK_URL=https://... ./openobserve/setup_alerts.sh` — idempotent, fires to any webhook (Slack, Discord, custom). Update URL in OO UI: Alerts → Destinations → agentguard-webhook.

---

### [done] #12 Prometheus metrics ingestion (~1h)

**Why:** rag-api exposes `/metrics` (prometheus_fastapi_instrumentator) and LiteLLM exposes Prometheus metrics. OpenObserve can scrape both, consolidating metrics + traces + logs in one platform.

**How:** Added `remote_write` block to `prometheus.yml` pointing at OpenObserve's Prometheus ingestion endpoint (`/api/default/prometheus/api/v1/write`). Credentials read from `ZO_ROOT_USER_EMAIL`/`ZO_ROOT_USER_PASSWORD` env vars (already set in `.env`). Prometheus scrapes rag-api, litellm, and otel-collector every 15s and forwards all time-series to OpenObserve. Requires infra stack running (`docker compose -f docker-compose.infra.yml up -d`). In OpenObserve: Streams → `prometheus` stream type to query metrics.

Here's a precise handover prompt for Claude Code:

---

### [done] #13 Surface per-experiment cost in AgentGuard's experiment runner**

In `app/eval/experiments.py`, the `run_experiment()` function compares multiple models against a Langfuse dataset. LiteLLM already returns token usage in its responses. The goal is to capture and surface cost per model per experiment run.

**What to do:**

1. In the experiment runner, capture `usage` (prompt_tokens, completion_tokens) from LiteLLM responses for each dataset item evaluated. LiteLLM exposes this on the response object as `response.usage` — it also has `response._hidden_params["response_cost"]` which is the pre-calculated USD cost per call.

2. Aggregate per model: total cost (USD), total prompt tokens, total completion tokens, cost per item (mean), and cost/quality ratio (cost divided by mean faithfulness score if available).

3. Surface this in `print_results()` as an additional cost summary table alongside the existing quality metrics table.

4. Also write the cost breakdown into the Langfuse experiment metadata so it's visible in the UI — use `langfuse.score()` or tag it on the dataset run object.

5. Add a `--cost-report` flag to the CLI (`app/main.py evaluate`) that prints the cost table even when running a single model (no comparison needed).

**Constraints:**
- LiteLLM proxy is the only LLM call path — do not add direct SDK calls
- All models are defined in `litellm_config.yaml`; cost data comes from LiteLLM responses, not hardcoded pricing tables
- Tests live in `tests/test_evaluators.py` and `tests/test_integration.py` — add unit tests for the cost aggregation logic, mock `response._hidden_params`
- Keep backward compatibility: `run_experiment()` signature unchanged, cost data is additive

**Files to touch:** `app/eval/experiments.py`, `app/main.py`, `tests/test_evaluators.py` (or new `tests/test_experiments.py`)