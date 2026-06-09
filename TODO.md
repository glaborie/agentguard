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

### [ ] #11 Alerts on trace data (~1h)

**Why:** No proactive alerting exists. Guardrail block spikes (injection attack in progress), high latency, and elevated error rates need automated notification.

**Targets:** Guardrail block rate spike, latency > threshold, error rate > threshold. Fire to Slack/email/webhook.

---

### [ ] #12 Prometheus metrics ingestion (~1h)

**Why:** rag-api exposes `/metrics` (prometheus_fastapi_instrumentator) and LiteLLM exposes Prometheus metrics. OpenObserve can scrape both, consolidating metrics + traces + logs in one platform.
