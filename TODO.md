# TODO — SOTA Gaps (SOTA scan 2026-06-02)

All additive — no architectural change required. Independent, can be parallelized.

---

## Direct peer gaps

### [!] #1 ML/semantic injection detection (~2d)

**Why:** Regex fails on paraphrased jailbreaks ("Act as if you have no rules" bypasses most patterns). LLM Guard's deberta model catches semantic variants that the 12 regex patterns in `guardrails/custom_guardrails.py` miss.

**Reference:** `protectai/llm-guard` → PromptInjection scanner (uses `protectai/deberta-v3-base-prompt-injection-v2`)

**Step 1:** In `guardrails/custom_guardrails.py`, add a second detection pass after the regex pre-filter (regex stays as fast microsecond gate; model only runs when regex does NOT block):
- Option A: add `llm-guard` as a dep and call `PromptInjectionScanner.scan()`
- Option B: load `transformers` zero-shot classifier directly (no llm-guard dep)
- Option C: call LiteLLM with a tiny guard prompt to classify intent

**Verify first:** Confirm `protectai/deberta-v3-base-prompt-injection-v2` is publicly accessible on HF hub (not gated) and fits within the 15 GB Docker RAM budget alongside existing services.

---

### [!] #2 CI/CD pipeline integration (~4h)

**Why:** `scripts/regression_gate.py` already exits 0/1/2 correctly — but no `.github/workflows/` file ships with the repo. Teams cloning AgentGuard must hand-wire CI themselves. DeepEval ships a ready-to-copy GitHub Actions template.

**Reference:** `confident-ai/deepeval` → `.github/workflows/` (uses `deepeval test run` with thresholds)

**Step 1:** Create `.github/workflows/regression-gate.yml` that runs:
```
python -m scripts.regression_gate --limit 5        # smoke on every PR
python -m scripts.regression_gate --dataset rag-golden-set  # full on main merge
```
Wire to `pull_request` events on `main`.

**Verify first:** Confirm whether the gate can run in stub/mock mode without a live Langfuse+Qdrant stack, or document it as a "requires live stack" gate and wire it to a separate on-demand workflow.

---

### [!] #3 Toxic/harmful content detection (~1d)

**Why:** Injection blocking + PII masking each guard one attack vector. Toxic/abusive inputs are a separate real-world failure mode not covered by either existing guard.

**Reference:** `protectai/llm-guard` → `llm_guard/input_scanners/toxicity.py` (uses `unitary/unbiased-toxic-roberta`)

**Step 1:** In `guardrails/custom_guardrails.py`, add `ToxicityGuard(CustomGuardrail)` with `async_pre_call_hook`:
- Option A: use `llm-guard` as a library (reuse their scanner)
- Option B: load a HuggingFace toxicity classifier directly (`unitary/unbiased-toxic-roberta` or `martin-ha/toxic-comment-model`)

**Verify first:** Confirm chosen HF model runs within Docker RAM budget and benchmark p95 latency — this adds to every request's hot path.

---

## Maturity / quality gaps

### [~] #4 Coverage reporting / badge (~2h)

**Why:** README has no coverage badge. DeepEval and Phoenix both display >90% badges. 263 unit tests exist but no `pytest-cov` is configured.

**Reference:** `confident-ai/deepeval` → `pyproject.toml` (coverage config + Codecov integration)

**Step 1:** Add `pytest-cov` to `requirements.txt`. In `pyproject.toml` under `[tool.pytest.ini_options]`, add:
```
addopts = "--cov=app --cov-report=term-missing"
```
Then add a Codecov badge to `README.md`.

---

### [~] #5 Type annotation completeness (~1d)

**Why:** `app/eval/benchmark.py` and `scripts/` lack consistent type annotations. Guardrails AI enforces pyright strict; this repo has no mypy/pyright config.

**Reference:** `guardrails-ai/guardrails` → `pyproject.toml` (pyright strict mode)

**Step 1:** Add `pyright` to `pyproject.toml` dev deps and run once to get a baseline error count. Fix `scripts/` and `app/eval/benchmark.py` first — highest annotation debt.

---

## Docs / onboarding gaps

### [~] #6 Cloud deployment guide (~2d)

**Why:** README says "Google Cloud deployment is planned" but no Terraform, Helm chart, or GCP guide exists. Phoenix ships Kubernetes manifests; Haystack ships enterprise deployment docs.

**Reference:** `Arize-ai/phoenix` → deployment docs and Docker Compose variants

**Step 1:** Create `docs/deployment/google-cloud.md` starting with Cloud Run (stateless services) + Cloud SQL + Memorystore. Identify which services need stateful persistence (Postgres, Qdrant, Redis, MinIO) before committing to architecture.

**Verify first:** Decide Cloud Run vs. GKE — Cloud Run is simpler for a first guide but Qdrant and MinIO need persistent volumes.

---

### [~] #7 CONTRIBUTING.md + local dev setup (~2h)

**Why:** No `CONTRIBUTING.md`. New contributors must reverse-engineer setup from `README.md`. Phoenix and Haystack both ship detailed contributor guides.

**Reference:** `deepset-ai/haystack` → `CONTRIBUTING.md`

**Step 1:** Create `CONTRIBUTING.md` covering: venv setup, running unit tests (`pytest -m "not integration"`), running the full stack (`docker compose up -d`), and submitting a PR.
