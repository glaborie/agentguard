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

**OpenTelemetry pipeline.** Two trace pipelines run in parallel: Langfuse SDK (`CallbackHandler`) for LLM-native tracing (token counts, prompt/completion capture) and OTel for full request lifecycle (HTTP ingress, httpx outbound calls, Qdrant queries). App sends OTLP/HTTP to `otel-collector` service, which fans out to Jaeger (UI: `:16686`), Langfuse's OTel ingestion endpoint (`/api/public/otel`), and OpenObserve (UI: `:5080`). Each request's OTel trace ID injected into Langfuse trace metadata (`otel_trace_id`) for cross-navigation. Auto-instruments FastAPI and httpx via `opentelemetry-instrumentation-fastapi` / `opentelemetry-instrumentation-httpx`. Set `OTEL_ENABLED=false` in `.env` to disable. Auth to Langfuse uses `LANGFUSE_OTEL_AUTH` env var (Basic auth, base64 of public_key:secret_key); default matches dev keys.

**OpenObserve observability.** OpenObserve (`:5080`) runs in the main stack (`docker-compose.yml`). Receives OTel traces via collector fan-out (stream `default`, stream_type `traces`) and container logs via Promtail (stream `default`, stream_type `logs`). LLM dashboard at `openobserve/dashboards/agentguard_llm.json` — 8 panels using real span field names. Four scheduled alerts via `openobserve/setup_alerts.sh` fire to configurable webhook. Note: OTel traces originate from `rag-api` app only — LiteLLM proxy spans go to Arize directly. Guardrail blocks (LiteLLM 400) don't produce OTel spans; they appear in Langfuse as ERROR-level `guardrail_block` traces instead. The log-based alert (`agentguard-guardrail-block-log`) catches all guard types by watching Docker logs via Promtail — more reliable than the trace-based alert for guardrail events. Alert history endpoint (`/api/default/alerts/history`) returns 404 in community edition v0.91; use `last_triggered_at` on alert objects or OpenObserve UI Alerts tab.

## Key files

See `.claude/agentguard-files.md` for full file inventory (infrastructure, app core, CLI, API, RAG, agent, eval, scripts).

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

python -m app.main debug-retrieval "query"                        # Show retrieved chunks with scores (compare mode)
python -m app.main debug-retrieval "query" --mode vector --k 4   # Vector-only, top-4
python -m app.main debug-retrieval "query" --mode hybrid --json  # Hybrid, raw JSON output
python -m app.main drift-check                                    # Detect quality regressions from Langfuse score history
python -m app.main drift-check --fail-on-regression              # Exit 1 if regression detected (CI gate)
python -m app.main drift-check --days 30 --threshold faithfulness=0.03  # Custom window + threshold
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

### Quality drift monitoring

`app/eval/drift.py` detects metric regressions by comparing two consecutive 7-day windows from Langfuse score history. `check_drift(df)` is a pure function (no Langfuse dependency) — pass it any DataFrame with columns `[timestamp, trace_id, metric, value, model]`. `fetch_scores_from_langfuse(days=14)` returns that DataFrame from live data. To add a new tracked metric, add it to `score_names` in `fetch_scores_from_langfuse()` and optionally set a default threshold in `_DEFAULT_THRESHOLDS`. For metrics where higher = worse, add the name to `_HIGHER_IS_WORSE`. Notebook: `notebooks/quality_drift.ipynb` (set `USE_SYNTHETIC_DATA = True` on fresh installs).

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

**Arize AX tracing (LiteLLM proxy layer).** Every LLM call is traced to Arize via the built-in `arize` success/failure callback in `litellm_config.yaml`. LiteLLM uses `openinference-instrumentation-litellm` to emit OTLP HTTP spans to `https://otlp.eu-west-1a.arize.com/v1` (EU region). Auth is via `ARIZE_SPACE_KEY` + `ARIZE_API_KEY` headers; project name is set via `ARIZE_PROJECT_NAME` (default: `agentguard`). Each request produces two spans: `litellm_request` (root — captures guardrails, model, cost metadata) and `raw_gen_ai_request` (child — captures exact OpenAI wire format). Coexists with Langfuse and Prometheus callbacks; all three fire independently per request. Required env vars: `ARIZE_SPACE_KEY`, `ARIZE_API_KEY`, `ARIZE_HTTP_ENDPOINT`, `ARIZE_PROJECT_NAME`.

**Semantic cache (LiteLLM proxy layer, always active when `SEMANTIC_CACHE_ENABLED=true`):** `guardrails/semantic_cache.py` implements `QdrantSemanticCache(BaseCache)`. On each LLM request: embeds the messages via `nomic-embed-text` (Ollama), searches the `semantic-cache` Qdrant collection for a cosine-similar vector above threshold (`SEMANTIC_CACHE_THRESHOLD`, default 0.85), and if found returns the cached response from Redis. Registered via `litellm_settings.callbacks` — the module-level code sets `litellm.cache = QdrantSemanticCache()` when LiteLLM imports the callback class at startup. Cache writes store the vector in Qdrant and the serialized response in Redis with `SEMANTIC_CACHE_TTL` TTL. All errors are non-fatal: failures return `None` and fall through to the LLM.

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
- Ollama serves only embedding model (`nomic-embed-text`). Model is baked into the image via `Dockerfile.ollama` — no manual pull needed after first `docker compose build`. All chat LLM calls go through OpenRouter via LiteLLM.
- `ingest` command uses `force_recreate=True` on Qdrant collection, so re-running wipes and rebuilds entire index. `QdrantClient` and `QdrantVectorStore.from_documents` both use `timeout=120` to handle slow collection operations under resource pressure.
- **Default model is `openrouter-gemini-flash`.** Both chat generation and DeepEval judge calls use this by default. Override with `--model openrouter-mistral` or set `DEFAULT_MODEL` / `DEEPEVAL_MODEL` in `.env`.
- **MinIO S3 credentials must be passed to Langfuse.** Langfuse v3 uses S3-compatible storage (MinIO) for event and media uploads. Without `LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID` / `SECRET_ACCESS_KEY` in Langfuse environment, AWS SDK falls back to instance metadata and fails with "Could not load credentials from any providers", causing span export errors ("Transient error Internal Server Error"). docker-compose references `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` from `.env`.
- **MinIO `langfuse` bucket must exist.** `minio-init` container creates it automatically. If S3 upload errors appear after wiping volumes, check bucket exists: `docker exec <minio-container> mc alias set local http://localhost:9000 minio miniosecret && mc ls local/langfuse`.
- **Redis requires password.** Redis container started with `--requirepass` using `REDIS_PASSWORD` from `.env`. Langfuse authenticates via `REDIS_AUTH`. If `.env` has `REDIS_PASSWORD` but Redis not configured to require it, worker logs "ERR AUTH called without any password configured" warnings.
- **langfuse-worker Redis socket timeout errors are expected.** `@langfuse/shared` hardcodes `socketTimeout: 30000` on all ioredis connections (prevents hung `moveToCompleted()` from blocking concurrency slots forever). Fires every ~30s on idle BullMQ connections. `REDIS_SOCKET_TIMEOUT_MS` env var ignored in this build — value not read by BullMQ's connection path. BullMQ auto-reconnects after each timeout; worker remains healthy and jobs not lost. Error spam is cosmetic.
- **All outbound HTTP calls use 60s timeout.** Langfuse SDK client (`app/core/tracing.py`) and all `httpx` calls in `scripts/` use `timeout=60` to tolerate slow responses from resource-constrained local Docker stack. Increase if timeouts appear on very slow hardware.

## Project layout

- [`FILETREE.md`](./FILETREE.md) — per-file index; read before `ls` / `grep` to locate any file