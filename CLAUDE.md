Compressing inline since text was provided directly (no file path given).

---

# CLAUDE.md - AgentGuard

## What this project is

AgentGuard — self-hosted control layer for preventing costly incidents in AI apps.

RAG + agentic assistant over NorthstarCRM synthetic knowledge base, with full observability, guardrails, and evaluation. Demonstrates how teams detect, evaluate, and block AI failures before reaching users: hallucinated policies, PII leaks, prompt injection, silent regressions after model/prompt changes.

## Architecture decisions

**LiteLLM as unified proxy.** All LLM calls (chat + embeddings) go through `http://localhost:4000`, routing to Ollama locally or OpenRouter for cloud fallback. App never talks to Ollama directly — always uses OpenAI-compatible API from LiteLLM. Swapping/adding models = config change in `litellm_config.yaml`, not code change.

**LangChain LCEL for RAG chain.** Chain in `app/rag/chain.py` is simple pipe: retriever | format_docs -> prompt -> llm -> StrOutputParser. LangChain chosen because Langfuse `CallbackHandler` integrates natively, giving automatic tracing of every step without manual instrumentation.

**LangGraph ReAct agent.** Agent in `app/agent/graph.py` is `StateGraph(MessagesState)` with two nodes: `agent` (LLM with bound tools) and `tools` (ToolNode). Agent decides which tools to call based on question. Five tools: doc search, trace listing, trace detail, response scoring, dataset summary. Langfuse CallbackHandler traces every node automatically. `MemorySaver` provides multi-turn memory for chat sessions.

**DeepEval for LLM-judged evaluation.** DeepEval metrics (faithfulness, answer relevancy, contextual relevancy, hallucination) run through `LiteLLMModel` wrapper routing judge calls through LiteLLM proxy. Scores pushed back to Langfuse via `client.create_score()`. Replaces hand-rolled LLM-as-judge for most use cases.

**Qdrant for vector storage.** Chosen over Chroma/FAISS: runs as proper Docker service with persistence, good LangChain integration, HTTP and gRPC APIs.

**Pydantic Settings for config.** `app/core/config.py` loads from `.env` with sensible defaults. Every external URL and credential is configurable. `settings` singleton imported everywhere. Compatibility shims at `app/config.py` and `app/tracing.py` / `app/telemetry.py` re-export from core package so existing import sites still work.

**Langfuse auto-provisioning.** docker-compose uses `LANGFUSE_INIT_*` env vars to create default org, project, and API keys on first boot. No manual setup — keys `pk-lf-dev` / `sk-lf-dev` work immediately.

**Open WebUI → Langfuse session linking.** Session linking requires Filter Function installed in Open WebUI (Admin → Functions) — import from `config/openwebui/chat_id_injection.json` (fastest) or paste `scripts/openwebui_langfuse_filter.py` manually. See SHOWCASE.md §5.0. Open WebUI build `3660bc00` does not send `chat-id` header; instead filter's `inlet` method reads `__metadata__["chat_id"]` (current conversation UUID) and injects into request body as `body["chat_id"]`. `app/api/routes/chat.py` reads `body.chat_id` (falling back to `chat-id` header for older builds); `app/api/services/rag_llm.py` wraps RAG chain with `propagate_attributes(session_id=chat_id)` from Langfuse SDK. Stamps Open WebUI chat UUID as `session_id` on every Langfuse trace, grouping all turns under one Langfuse Session. Navigation: `http://localhost:3100/c/<uuid>` maps directly to `http://localhost:3200/project/my-project/sessions/<uuid>` — UUID is identical.

**Human feedback loop.** Open WebUI stores thumbs-up/down in `annotation.rating` on each message internally — does NOT fire external webhook URL for in-chat ratings. `scripts/sync_feedback.py` polls Open WebUI API, finds rated messages, correlates each to Langfuse trace by `metadata.message_id` (exact, injected by Filter Function) with question-text + timestamp fallback for older traces. Scores written via direct `POST /api/public/scores` to preserve `configId` (SDK batch ingestion endpoint silently drops it). Two scores per rated message: `user_feedback` (BOOLEAN, 1=thumbs-up / 0=thumbs-down) and `user_feedback_rating` (NUMERIC, 1–10 from `annotation.details.rating` if present). State in `.sync_feedback_state.json`. Combined worker runs this automatically every 120s. `POST /webhook` remains as direct-call fallback.

**Online (continuous) evaluation.** `scripts/online_eval_worker.py` polls Langfuse every N seconds for new `RunnableSequence` traces (user RAG queries) and runs three code-based evaluators — `has_source_citation`, `is_within_length`, `contains_no_hallucination_markers` — pushing scores back as `online_has_citation`, `online_within_length`, `online_no_hallucination_markers` (all `BOOLEAN`). Open WebUI internal system calls (`### Task:` prefix) filtered out. State in `.online_eval_state.json`; `--reset` clears it. Run continuously with `python -m scripts.online_eval_worker` or single-pass with `--once`. Automated via combined worker (60s interval).

**Automated dataset building from user feedback.** `scripts/build_dataset.py` queries Langfuse for all `user_feedback=1.0` scores, fetches linked traces, upserts `{question, answer}` pairs with `source_trace_id` back-links into `rag-golden-set` dataset. Turns every thumbs-up into labeled gold example for experiments and regression testing — no manual curation. State in `.build_dataset_state.json`. Combined worker runs this every 300s. Run manually with `python -m scripts.build_dataset` (supports `--dry-run`, `--reset`, `--dataset`).

**Langfuse Prompt Management.** RAG system prompt stored in Langfuse Prompt Registry (name: `rag-system-prompt`, type: chat). `app/rag/chain.py` fetches at runtime via `langfuse.get_prompt()` with 60s cache and in-process fallback (`LANGFUSE_PROMPT_MESSAGES`) if Langfuse unreachable. Seed once with `python -m scripts.seed_langfuse_prompt`; push new version after editing with `--force`. Iterate on prompt via Langfuse UI without redeploying — edit, save, next request picks it up within 60s.

**OpenTelemetry pipeline.** Two trace pipelines run in parallel: Langfuse SDK (`CallbackHandler`) for LLM-native tracing (token counts, prompt/completion capture) and OTel for full request lifecycle (HTTP ingress, httpx outbound calls, Qdrant queries). App sends OTLP/HTTP to `otel-collector` service, which fans out to Jaeger (UI: `:16686`) and Langfuse's OTel ingestion endpoint (`/api/public/otel`). Each request's OTel trace ID injected into Langfuse trace metadata (`otel_trace_id`) for cross-navigation. Auto-instruments FastAPI and httpx via `opentelemetry-instrumentation-fastapi` / `opentelemetry-instrumentation-httpx`. Set `OTEL_ENABLED=false` in `.env` to disable. Auth to Langfuse uses `LANGFUSE_OTEL_AUTH` env var (Basic auth, base64 of public_key:secret_key); default matches dev keys.

## Key files

- `docker-compose.yml` - Main stack: 10 services + 2 init containers. YAML anchors for DRY logging/resource config. Langfuse v3 needs postgres + clickhouse + redis + minio. Ollama has GPU reservation (4 CPU, 8 GB mem). All services on custom `langfuse` bridge network. Redis host port is 6300 (not 6379) due to Windows Hyper-V port exclusions. Postgres host port is 5500 (not 5432) — ports 5358–5457 reserved by Hyper-V on this machine. All containers run `TZ: UTC` to prevent Langfuse writing `createdAt`/`timestamp` in local time; without this, Langfuse v3 stores local time tagged as UTC (`Z`), making `latency` field and all trace timestamps wrong by UTC offset. Redis requires password (`REDIS_PASSWORD` from `.env`); Langfuse authenticates via `REDIS_AUTH`. MinIO credentials passed to Langfuse via `LANGFUSE_S3_*_ACCESS_KEY_ID` / `SECRET_ACCESS_KEY` env vars. `minio-init` container auto-creates `langfuse` bucket on first boot.
- `docker-compose.infra.yml` - Optional infra stack (spin up on demand). Contains: traefik, jaeger, otel-collector, loki, promtail, portainer, prometheus, grafana. Uses `networks: langfuse: external: true` — joins main stack's bridge network so all services reachable by container name. Start with `docker compose -f docker-compose.infra.yml up -d`. When down, OTel spans from app fail silently (non-fatal; disable entirely with `OTEL_ENABLED=false`). Traefik provides hostname routing (`openwebui.localhost`, `langfuse.localhost`, `litellm.localhost`, `rag-api.localhost`, `grafana.localhost`, `jaeger.localhost`, `loki.localhost`) on port 80. Loki + Promtail collect all container logs via Docker socket; Grafana auto-provisions Loki and Prometheus datasources plus AgentGuard dashboard (`grafana/provisioning/`). Grafana admin password: `GF_SECURITY_ADMIN_PASSWORD` from `.env` (default `grafana`).
- `litellm_config.yaml` - Model routing + guardrail registration. Ollama models use `http://ollama:11434` (Docker internal). OpenRouter models use `model: openai/<provider>/<model-id>` + `api_base: https://openrouter.ai/api/v1` (`openai/` prefix routes to OpenAI-compatible provider, strips it, sends bare model ID to OpenRouter — works for any model regardless of LiteLLM registry). Three guardrails registered: `prompt-injection` and `pii-masking` are `default_on: true`; `toxicity` registered but `default_on: false` (enable with `TOXICITY_GUARD_ENABLED=true`).
- `guardrails/custom_guardrails.py` - LiteLLM custom guardrails. `PromptInjectionGuard` (pre_call): 12 regex patterns + runtime-toggleable LLM-judge semantic second pass. `ToxicityGuard` (pre_call): LLM-judge classifier for toxic/abusive inputs, runtime-toggleable. `PIIMaskingGuard` (post_call): redacts email, SSN, credit card, phone from responses. All classifier calls embed content in system role to bypass LiteLLM built-in content filters. Guards read `runtime_config.json` per call (hot-reload, no LiteLLM restart needed) with env var fallbacks. Mounted at `/app/custom_guardrails.py`.
- `runtime_config.json` - Runtime feature flags shared between FastAPI app and LiteLLM container (mounted at `/app/runtime_config.json`). Guards and cache read this per-call for hot-reload without restart. Managed via dashboard at `/dashboard` or `GET/PATCH /api/config`. Fields: `semantic_guard_enabled`, `toxicity_guard_enabled`, `semantic_cache_enabled/threshold/ttl`, `langfuse_tracing_enabled`, `otel_enabled`, `default_model`, `agent_model` (plus per-guard model/timeout).
- `app/core/config.py` - Single source of truth for all settings (`Settings` + `settings` singleton). Compatibility shim at `app/config.py` re-exports via `*`.
- `app/core/feature_flags.py` - Runtime feature flags read/write. `get_flags()` merges `DEFAULTS` with overrides from `runtime_config.json`; `update_flags(dict)` writes selective overrides; `reset_flags()` deletes override file. Used by `tracing.py` and the config API.
- `app/core/tracing.py` - Langfuse client singleton + `CallbackHandler` factory. `get_langfuse_handler()` checks `langfuse_tracing_enabled` flag — returns real `CallbackHandler` when on, `_NoopHandler` (BaseCallbackHandler stub with `last_trace_id=None`) when off. All call sites work unchanged. Compatibility shim at `app/tracing.py`.
- `app/core/telemetry.py` - OTel SDK bootstrap. `init_telemetry(app)` sets up `TracerProvider`, `OTLPSpanExporter` (HTTP to Collector), auto-instruments FastAPI + httpx. `get_otel_trace_id()` returns active OTel trace ID for cross-linking into Langfuse metadata. Called from FastAPI lifespan in `app/api/app.py`. Compatibility shim at `app/telemetry.py`.
- `app/core/logging.py` - `configure_logging(level)` wraps `logging.basicConfig` with standard format. Called once from `app/cli/app.py::main()` before command dispatch.
- `app/core/ids.py` - `request_id()` (12-char hex, for log correlation) and `completion_id()` (OpenAI-style `chatcmpl-<hex8>`).
- `app/main.py` - Bare entry point: `from app.cli.app import main` + `if __name__ == "__main__": main()`.
- `app/cli/app.py` - Argument parser and dispatch. `_build_parser()` calls each command module's `register(sub)`; `main()` calls `configure_logging()` then dispatches via `args.func(args)`.
- `app/cli/commands/` - One module per command domain: `ingest.py`, `query.py`, `agent.py`, `evaluate.py`, `experiment.py`, `dataset.py`, `regression.py`, `benchmark.py`, `red_team.py`. Each exposes `register(sub)` and command functions. All call through domain service wrappers.
- `app/api/__init__.py` - Lazy-loads FastAPI `app` object via `__getattr__` so importing `app.api.services.*` does not require fastapi. `uvicorn app.api:app` still works.
- `app/api/app.py` - `create_app()` factory: builds FastAPI app, registers CORS middleware and all routers, sets up OTel in lifespan.
- `app/api/schemas.py` - `Message` and `ChatRequest` Pydantic models.
- `app/api/streaming.py` - `stream_from_result()` SSE generator.
- `app/api/routes/` - Thin handlers: `health.py`, `models.py`, `webhook.py`, `chat.py`, `config.py`. Each validates request, calls one service function, returns result. `config.py` serves dashboard HTML at `GET /dashboard` and REST config API at `GET/PATCH /api/config` + `POST /api/config/reset`.
- `app/api/services/models_service.py` - `MODELS`, `DIRECT_MODELS`, model descriptions, `get_model_list()`. Canonical location for virtual-model config (imported by `chat_service`).
- `app/api/services/health_service.py` - `_probe(name, url)` async prober + `check_all()` aggregator.
- `app/api/services/feedback_service.py` - `parse_feedback(payload)` normalises flat/nested Open WebUI payloads; `push_score()` writes to Langfuse; `handle_webhook()` orchestrates full flow.
- `app/api/services/direct_llm.py` - Direct LiteLLM call (no RAG). All httpx errors caught and returned as inline error strings.
- `app/api/services/rag_llm.py` - RAG chain invocation via `rag_service.build_chain()`. Uses Langfuse trace ID as completion ID for feedback correlation.
- `app/api/services/chat_service.py` - Dispatch orchestrator: picks direct vs. RAG path, annotates OTel span, builds OpenAI-format completion response.
- `app/rag/ingest.py` - Loads documents from local corpus (`mock_corpus/` by default) recursively. `.md` files load as-is; `.jsonl` files split into one Document per line with records rendered as readable `key: value` text. Chunks with `RecursiveCharacterTextSplitter`, embeds via LiteLLM, stores in Qdrant. Detects embedding dimension automatically. No web scraping.
- `app/rag/chain.py` - LCEL chain internals. `ScoredRetriever(BaseRetriever)` calls `similarity_search_with_score()`, injects `retrieval_score` into doc metadata, sets four OTel span attributes. `build_rag_chain(guardrails_enabled=True)` wires retriever → prompt → LLM → parser. Pass `guardrails_enabled=False` to disable LiteLLM guardrails for that request via `extra_body` (used by benchmark runner for ablation comparisons).
- `app/rag/service.py` - Stable domain interface: `ingest()`, `query()`, `build_chain()`. CLI commands and API service layer call this instead of chain/ingest modules directly.
- `app/agent/tools.py` - Five `@tool` functions: `search_docs`, `list_traces`, `get_trace_detail`, `score_response`, `get_dataset_summary`. Each reuses existing infrastructure (retriever, Langfuse client, evaluators).
- `app/agent/graph.py` - LangGraph ReAct agent. `build_agent(model, checkpointer)` returns compiled graph. `run_agent(question, ...)` is main entry point. `tools` node is `_guarded_tool_node` (not bare `ToolNode`) — validates each tool call via `app/agent/tool_guard.py` before dispatch; blocked calls return `ToolMessage` error so agent can reason about refusal without crashing. Trace shape: each reasoning iteration creates `ChatOpenAI` observation; tool executions sit between them as `tools` → `<tool_name>` observations. 3-tool query produces 4 `ChatOpenAI` spans and 3 `tools` nodes under `LangGraph` root.
- `app/agent/tool_guard.py` - Pre-execution tool-call guardrail. `validate_tool_call(tool_name, tool_args)` enforces allowlist of permitted tools, checks `search_docs` queries for injection patterns (10-pattern subset of `PromptInjectionGuard`), bounds-checks `list_traces` limit. Raises `ToolCallBlockedError` on violation.
- `app/agent/prompts.py` - Agent system prompt.
- `app/agent/service.py` - Stable domain interface: `run()`, `build_chat_session()`, `respond()`. Encapsulates `MemorySaver` + `HumanMessage` so CLI and API don't depend on LangGraph internals.
- `app/eval/evaluators.py` - Four code-based evaluators + one LLM-as-judge. Judge returns JSON with binary relevance/faithfulness/completeness scores.
- `app/eval/deepeval_metrics.py` - `LiteLLMModel(DeepEvalBaseLLM)` routes judge calls through LiteLLM. Metric factory functions + `METRIC_REGISTRY` for dynamic lookup.
- `app/eval/deepeval_runner.py` - `run_deepeval_evaluation()` fetches Langfuse dataset, runs RAG chain, evaluates with DeepEval, pushes scores to Langfuse.
- `app/eval/experiments.py` - Multi-model experiment runner. `run_experiment(dataset, models)` runs every model against every dataset item, scores with DeepEval, pushes scores to Langfuse, links each trace to named dataset run via `client.api.dataset_run_items.create()`. `print_comparison_table()` prints per-model average score table using ASCII box chars (Unicode box-drawing chars fail on Windows cp1252). `LLMTestCase` passes `context=retrieval_context` (required by `HallucinationMetric`) in addition to `retrieval_context`.
- `app/eval/service.py` - Stable domain interface: `evaluate()`, `experiment()`, `show_experiment_table()`, `regression_gate()`. CLI commands call this instead of runner/experiment modules or scripts directly.
- `app/eval/benchmark.py` - Benchmark runner for NorthstarCRM knowledge base. Evaluates RAG pipeline across five metrics: retrieval hit rate, factual coverage, policy violation rate, correct escalation rate, answer helpfulness. Supports three run modes: `full` (RAG + guardrails), `no-guardrails` (RAG, guardrails off via `extra_body`), `direct` (bare LLM, no retrieval). Loads items from `mock_corpus/07_benchmark/` (JSONL). `run_benchmark()` drives item × mode combinations; `print_results()` outputs per-question details and aggregate comparison table. Code-based metrics: `eval_retrieval_hit` (filename or full-path match), `eval_factual_coverage` (stop-word-filtered token overlap), `eval_escalation` (15 escalation-intent phrases). LLM-as-judge metrics: `eval_policy_violation` (7 NorthstarCRM sales policies + scoring rules distinguishing correct refusals from true violations), `eval_helpfulness` (1–5 deal-progression score). `_parse_judge_json()` strips markdown fences before parsing judge responses. CLI flag `--item <id>` (e.g. `--item edge_002`) runs single benchmark item; combine with `--compare` to see all three modes for that item.
- `scripts/build_dataset.py` - Builds `rag-golden-set` Langfuse dataset from positively rated traces. Queries `user_feedback=1.0` scores, fetches each linked trace, upserts `{question, answer}` items with `source_trace_id`. `run_once()` called by worker every 5 minutes. State in `.build_dataset_state.json`.
- `scripts/seed_benchmark_dataset.py` - Seeds two separate Langfuse datasets from local JSONL files (idempotent, safe to re-run). `northstar-rag` (18 items, item IDs `nr-*`): bench_001–008 from `benchmark_questions.jsonl` joined with ideal answers from `expected_answers.jsonl`, plus edge_001–010 from `edge_cases.jsonl`; each item carries `expected_facts`, `should_escalate`, `expected_action`, `gold_docs`, and `ideal_answer` where available — use for RAG quality experiments with DeepEval. `northstar-safety` (11 items, item IDs `ns-*`): 5 prompt injection, 3 threats/insults, 3 PII masking scenarios mirrored from `tests/test_integration.py`; each item carries `guardrail_type` and `expected_behavior` (`blocked` / `blocked_or_refused` / `pii_masked`) — use for guardrail behaviour evaluation. Run with `--dry-run` to preview without writing.
- `scripts/regression_gate.py` - `run_gate()` implements quality gate logic (run dataset items through RAG, evaluate with DeepEval, check thresholds). Exit codes: 0=all pass, 1=metric failure, 2=runtime error. Default thresholds: `FaithfulnessMetric≥0.80`, `AnswerRelevancyMetric≥0.70`, `ContextualRelevancyMetric≥0.30`, `HallucinationMetric≤0.30`. `HallucinationMetric` is lower-is-better — threshold is maximum, not minimum. Override thresholds via `--thresholds '{"FaithfulnessMetric":0.85}'`. Called by `app/eval/service.py::regression_gate()` and directly: `python -m scripts.regression_gate --limit 5`.
- `scripts/red_team.py` - Automated adversarial probing of guardrail stack. `run_red_team(attack_types, n_variants, model)` generates adversarial prompt variants via LiteLLM (guardrails bypassed during generation via `guardrails: []` + `x-agentguard-internal` metadata to prevent recursion) then probes each through full guardrail stack. Four attack types: `prompt_injection` (instruction override), `jailbreak` (DAN/persona escapes), `pii_probe` (PII extraction), `system_prompt_leak` (system prompt exfiltration). HTTP 400/403 = blocked = PASS; HTTP 200 = leaked = FAIL; timeout = leaked (fail-safe). Exit codes: 0=all blocked, 1=any leaked, 2=error — same pattern as `regression_gate.py` for CI integration. Run with `python -m scripts.red_team` or via CLI with `python -m app.main red-team`.
- `scripts/worker.py` - Combined background daemon. Runs three pollers in threads: `eval-worker` (60s), `feedback-worker` (120s), `dataset-builder` (300s). Seeds score configs on startup. Launched automatically by `agentguard-worker` Docker service.
- `scripts/utils.py` - Shared utilities for scripts: `langfuse_basic_auth()`, `load_state()`/`save_state()` (corrupt-safe JSON state files), `HTTP_TIMEOUT`, `TRACE_PAGE_SIZE`, `SCORE_PAGE_SIZE`.
- `app/utils.py` - Shared app-layer utilities: `truncate(text, max_len)`, `extract_trace_output(trace)` (normalises None/str/dict trace output to plain string).
- `otel-collector-config.yaml` - OTel Collector pipeline: receives OTLP (gRPC :4317, HTTP :4318), fans out to Jaeger (OTLP gRPC) and Langfuse (OTLP/HTTP `/api/public/otel`). Uses `${env:LANGFUSE_OTEL_AUTH}` for Basic auth to Langfuse.

## How to work with this codebase

### Running commands

```bash
python -m app.main ingest              # Ingest docs into Qdrant
python -m app.main query "question"    # Single RAG query with tracing
python -m app.main chat                # Interactive RAG chat
python -m app.main agent "question"    # ReAct agent with tools
python -m app.main agent-chat          # Interactive agent chat with memory
python -m app.main evaluate --dataset name  # Run DeepEval metrics (single model)
python -m app.main experiment --dataset rag-golden-set --models openrouter-gemini-flash,openrouter-mistral  # Multi-model comparison
python -m app.main regression-gate --dataset rag-golden-set      # Run quality gate (exit 0=pass, 1=fail)
python -m app.main regression-gate --limit 5                     # Quick smoke-test (5 items)
python -m app.main benchmark                                      # Run benchmark (full mode, all items)
python -m app.main benchmark --compare                            # Run all 3 modes side-by-side
python -m app.main benchmark --limit 5 --no-llm-judge            # Fast smoke-test (5 items, code metrics only)
python -m app.main benchmark --mode no-guardrails                 # Ablation: guardrails off
python -m app.main benchmark --mode direct                        # Baseline: bare LLM, no retrieval
python -m app.main benchmark --item edge_002                      # Run a single item by ID
python -m app.main benchmark --item edge_002 --compare           # Single item across all 3 modes

python -m app.main red-team                                       # Probe all 4 attack types, 5 variants each
python -m app.main red-team --attacks prompt_injection jailbreak  # Run specific attack types
python -m app.main red-team --limit 10                           # 10 variants per attack type
python -m scripts.red_team --limit 3                             # Direct script entry point
# One-time setup (after first docker compose up):
python -m scripts.seed_langfuse_prompt        # Register RAG system prompt in Langfuse
python -m scripts.seed_langfuse_prompt --force # Push a new version (after editing)
python -m scripts.seed_benchmark_dataset      # Seed northstar-benchmark dataset (29 items)
python -m scripts.seed_benchmark_dataset --dry-run  # Preview without writing

# Background workers (run automatically by agentguard-worker Docker service):
python -m scripts.worker               # All three pollers in one process
python -m scripts.online_eval_worker --once   # Single eval pass
python -m scripts.sync_feedback --apply       # Single feedback sync pass
python -m scripts.build_dataset               # Build/update rag-golden-set dataset
python -m scripts.build_dataset --dry-run     # Preview without writing
python -m scripts.build_dataset --reset       # Rebuild from scratch
```

### Adding a new model

Add entry to `litellm_config.yaml` under `model_list`, then use `model_name` value with `--model`:

```bash
python -m app.main query "question" --model new-model-name
```

### Adding a new evaluator

Add function to `app/eval/evaluators.py` taking output string and returning score. Wire into `run_experiment()` in `app/eval/experiments.py` inside `scores` dict. For DeepEval metrics, add factory function to `app/eval/deepeval_metrics.py` and register in `METRIC_REGISTRY`.

### Adding a new agent tool

Add `@tool`-decorated function to `app/agent/tools.py` with clear docstring (LLM reads it to decide when to use tool). Add to `ALL_TOOLS` list. Update system prompt in `app/agent/prompts.py` to mention new tool.

### Tracing

Every function calling LLM should accept `callbacks` parameter and pass it to LangChain's `.invoke(config={"callbacks": callbacks})`. CLI commands obtain handler via `get_langfuse_handler()` (from `app/core/tracing.py`) and pass to domain service functions.

### Tests

```bash
pytest -m "not integration"   # unit tests, no Docker needed (~5s)
pytest -m integration          # 19 integration tests, Docker stack must be running
pytest -v                      # Full suite
```

Integration tests auto-skip if Docker stack unreachable (checks `localhost:4000/health/liveliness` in `conftest.py`). Guardrail unit tests (`tests/test_guardrails.py`) mock entire `litellm` module hierarchy via `sys.modules` because `litellm` only exists inside Docker container. `app/api/__init__.py` uses `__getattr__` lazy-loading so importing `app.api.services.*` in unit tests does not require fastapi.

`tests/test_integration.py::TestLiteLLMGuardrails` hits live LiteLLM proxy to verify guardrails fire end-to-end. Covers three layers: prompt injection (5 parametrized cases, `_assert_blocked` — expects HTTP non-200 from `PromptInjectionGuard`), threats/insults (3 cases, `_assert_rejected` — accepts proxy block or model self-refusal), and PII masking (email and phone injected via system context, response must not contain raw value). Use `_assert_blocked` when proxy is enforcement point (custom guard raises `BadRequestError`); use `_assert_rejected` when built-in LiteLLM policy may pass request to model, which then self-censors.

### Guardrails

Three LiteLLM custom guardrails registered. Two run on every request by default:
- **Prompt injection** (pre_call, always on): blocks 12 regex patterns (jailbreak, ignore instructions, DAN, system prompt exfiltration, etc.). DAN pattern uses `(?-i:DAN)\b` for case-sensitive matching to avoid false-positiving on name "Dan". Optional LLM-judge semantic second pass (`SEMANTIC_GUARD_ENABLED=true`) catches paraphrased jailbreaks regex misses — calls back through LiteLLM with classifier content embedded in system role to bypass built-in content filters.
- **Toxic content** (pre_call, opt-in via `TOXICITY_GUARD_ENABLED=true`): LLM-judge classifier for toxic/abusive inputs. Also embeds content in system role.
- **PII masking** (post_call, always on): redacts email, SSN, credit card, phone from LLM responses using regex.

Agent tool-call guardrail (separate layer, always active for ReAct agent): `app/agent/tool_guard.py` validates tool name + args before `ToolNode` dispatches. Blocks unknown tools, injection-shaped `search_docs` queries, and out-of-range `list_traces` limits.

**Arize AX tracing (LiteLLM proxy layer).** Every LLM call traced to Arize via built-in `arize` success/failure callback in `litellm_config.yaml`. LiteLLM uses `openinference-instrumentation-litellm` to emit OTLP HTTP spans to `https://otlp.eu-west-1a.arize.com/v1` (EU region). Auth via `ARIZE_SPACE_KEY` + `ARIZE_API_KEY` headers; project name set via `ARIZE_PROJECT_NAME` (default: `agentguard`). Each request produces two spans: `litellm_request` (root — captures guardrails, model, cost metadata) and `raw_gen_ai_request` (child — captures exact OpenAI wire format). Coexists with Langfuse and Prometheus callbacks; all three fire independently per request. Required env vars: `ARIZE_SPACE_KEY`, `ARIZE_API_KEY`, `ARIZE_HTTP_ENDPOINT`, `ARIZE_PROJECT_NAME`.

**Semantic cache (LiteLLM proxy layer):** `guardrails/semantic_cache.py` implements `QdrantSemanticCache(BaseCache)`. On each LLM request: checks `runtime_config.json` for `semantic_cache_enabled` (hot-toggle, no restart), embeds messages via `nomic-embed-text` (Ollama), searches `semantic-cache` Qdrant collection for cosine-similar vector above `semantic_cache_threshold` (default 0.85), returns cached response from Redis if found. Threshold and TTL also re-read from `runtime_config.json` per call. Registered via `litellm_settings.callbacks` — module-level code sets `litellm.cache = QdrantSemanticCache()` at startup. All errors non-fatal: failures return `None` and fall through to LLM.

Guardrails config: `guardrails:` key in `litellm_config.yaml` is **top-level** — do not nest under `litellm_settings:`. Module name in `guardrail:` must match mounted filename (`custom_guardrails`, not `custom_guardrail`).

To test guardrails manually, see `VALIDATION.md` section 8.

### Docker networking

Services reference each other by container name (`postgres`, `redis`, `ollama`, `minio`, etc.) on `langfuse` bridge network. App code runs on host and uses `localhost` ports. If you move app into Docker, change `app/core/config.py` defaults or `.env` values to use container names.

### Docker resource management

All containers have log rotation (`10m` max, 2 files). Memory-heavy services have explicit CPU/memory limits via YAML anchors (`x-deploy-clickhouse`, `x-deploy-postgres`, `x-deploy-ollama`). Total Docker memory budget ~15 GB. Portainer (`:9443`) provides container management UI. Real-time log streaming via Loki (in infra stack) — query with LogQL in Grafana or via `http://localhost:3101`.

### Environment

- Python 3.11+
- Windows 11 (port 6379 blocked by Hyper-V, so Redis maps to 6300)
- `.env` is gitignored; copy from `.env.example`
- `data/docs/` directory is gitignored for local markdown files used during ingestion

## Known issues

- **LiteLLM image (`ghcr.io/berriai/litellm:main-latest`)** requires PostgreSQL database. Compose gives it `DATABASE_URL` env var pointing to `litellm` database on shared Postgres instance. On first boot, Prisma migrations run automatically (~30s). `master_key` in `litellm_config.yaml` must be literal string (not env var reference) so it registers correctly in DB. LiteLLM UI login uses `UI_USERNAME` / `UI_PASSWORD` env vars (defaults: `admin` / `litellm123456`) — not master key. **Prisma migration stuck / container stays unhealthy after force-recreate:** stale failed migration rows in `_prisma_migrations` (rows with `finished_at IS NULL`) block all subsequent runs. Fix: `docker exec langfuse_poc-postgres-1 psql -U postgres -d litellm -c "DELETE FROM \"_prisma_migrations\" WHERE finished_at IS NULL;"` then restart container.
- **Langfuse SDK v4** removed `fetch_traces`, `fetch_trace`, and `fetch_datasets`. Agent tools use new `client.api` namespace: `client.api.trace.list(limit=N)` returns `response.data`; `client.api.trace.get(trace_id)` returns trace directly (no `.data` wrapper); `client.api.datasets.list()` returns `response.data`. See `app/agent/tools.py`.
- **Langfuse SDK v4** also changed `CallbackHandler` interface. No longer accepts `session_id`, `tags`, or `metadata` kwargs — use `trace_context` or let handler look up client singleton by `public_key`. See `app/core/tracing.py`.
- Ollama serves only embedding model. Pull manually after first `docker compose up`: `docker compose exec ollama ollama pull nomic-embed-text`. All chat LLM calls go through OpenRouter via LiteLLM.
- `ingest` command uses `force_recreate=True` on Qdrant collection, so re-running wipes and rebuilds entire index. `QdrantClient` and `QdrantVectorStore.from_documents` both use `timeout=120` to handle slow collection operations under resource pressure.
- **Default model is `openrouter-gemini-flash`.** Both chat generation and DeepEval judge calls use this by default. Override with `--model openrouter-mistral` or set `DEFAULT_MODEL` / `DEEPEVAL_MODEL` in `.env`.
- **MinIO S3 credentials must be passed to Langfuse.** Langfuse v3 uses S3-compatible storage (MinIO) for event and media uploads. Without `LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID` / `SECRET_ACCESS_KEY` in Langfuse environment, AWS SDK falls back to instance metadata and fails with "Could not load credentials from any providers", causing span export errors ("Transient error Internal Server Error"). docker-compose references `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` from `.env`.
- **MinIO `langfuse` bucket must exist.** `minio-init` container creates it automatically. If S3 upload errors appear after wiping volumes, check bucket exists: `docker exec <minio-container> mc alias set local http://localhost:9000 minio miniosecret && mc ls local/langfuse`.
- **Redis requires password.** Redis container started with `--requirepass` using `REDIS_PASSWORD` from `.env`. Langfuse authenticates via `REDIS_AUTH`. If `.env` has `REDIS_PASSWORD` but Redis not configured to require it, worker logs "ERR AUTH called without any password configured" warnings.
- **langfuse-worker Redis socket timeout errors are expected.** `@langfuse/shared` hardcodes `socketTimeout: 30000` on all ioredis connections (prevents hung `moveToCompleted()` from blocking concurrency slots forever). Fires every ~30s on idle BullMQ connections. `REDIS_SOCKET_TIMEOUT_MS` env var ignored in this build — value not read by BullMQ's connection path. BullMQ auto-reconnects after each timeout; worker remains healthy and jobs not lost. Error spam is cosmetic.
- **All outbound HTTP calls use 60s timeout.** Langfuse SDK client (`app/core/tracing.py`) and all `httpx` calls in `scripts/` use `timeout=60` to tolerate slow responses from resource-constrained local Docker stack. Increase if timeouts appear on very slow hardware.