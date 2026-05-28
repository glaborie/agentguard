# CLAUDE.md - AgentGuard

## What this project is

AgentGuard — a self-hosted control layer for preventing costly incidents in AI applications.

A RAG + agentic assistant over the NorthstarCRM synthetic knowledge base, with full observability, guardrails, and evaluation built in. Demonstrates how teams can detect, evaluate, and block AI failures before they reach users: hallucinated policies, PII leaks, prompt injection, and silent regressions after model or prompt changes.

## Architecture decisions

**LiteLLM as a unified proxy.** All LLM calls (chat + embeddings) go through `http://localhost:4000`, which routes to Ollama locally or OpenRouter for cloud fallback. The app never talks to Ollama directly - it always uses the OpenAI-compatible API from LiteLLM. This means swapping or adding models is a config change in `litellm_config.yaml`, not a code change.

**LangChain LCEL for the RAG chain.** The chain in `app/rag/chain.py` is a simple pipe: retriever | format_docs -> prompt -> llm -> StrOutputParser. LangChain was chosen because the Langfuse `CallbackHandler` integrates natively with it, giving automatic tracing of every step without manual instrumentation.

**LangGraph ReAct agent.** The agent in `app/agent/graph.py` is a `StateGraph(MessagesState)` with two nodes: `agent` (LLM with bound tools) and `tools` (ToolNode). The agent decides which tools to call based on the question. Five tools are available: doc search, trace listing, trace detail, response scoring, and dataset summary. The Langfuse CallbackHandler traces every node automatically. `MemorySaver` provides multi-turn memory for chat sessions.

**DeepEval for LLM-judged evaluation.** DeepEval metrics (faithfulness, answer relevancy, contextual relevancy, hallucination) run through a `LiteLLMModel` wrapper that routes judge calls through the same LiteLLM proxy. Scores are pushed back to Langfuse via `client.create_score()`. This replaces the need for the hand-rolled LLM-as-judge for most use cases.

**Qdrant for vector storage.** Chosen over Chroma/FAISS because it runs as a proper service in Docker with persistence, has a good LangChain integration, and provides both HTTP and gRPC APIs.

**Pydantic Settings for config.** `app/core/config.py` loads from `.env` with sensible defaults. Every external URL and credential is configurable. The `settings` singleton is imported everywhere. Compatibility shims at `app/config.py` and `app/tracing.py` / `app/telemetry.py` re-export from the core package so existing import sites still work.

**Langfuse auto-provisioning.** The docker-compose uses `LANGFUSE_INIT_*` env vars to create a default org, project, and API keys on first boot. No manual setup needed - keys `pk-lf-dev` / `sk-lf-dev` work immediately.

**Open WebUI → Langfuse session linking.** Session linking requires a Filter Function installed in Open WebUI (Admin → Functions) — import from `config/openwebui/chat_id_injection.json` (fastest) or paste `scripts/openwebui_langfuse_filter.py` manually. See SHOWCASE.md §5.0. Open WebUI build `3660bc00` does not send a `chat-id` header; instead, the filter's `inlet` method reads `__metadata__["chat_id"]` (the current conversation UUID) and injects it into the request body as `body["chat_id"]`. `app/api/routes/chat.py` reads `body.chat_id` (falling back to the `chat-id` header for older builds); `app/api/services/rag_llm.py` wraps the RAG chain with `propagate_attributes(session_id=chat_id)` from the Langfuse SDK. This stamps the Open WebUI chat UUID as `session_id` on every Langfuse trace, grouping all turns of a conversation under one Langfuse Session. Navigation: `http://localhost:3001/c/<uuid>` maps directly to `http://localhost:3000/project/my-project/sessions/<uuid>` — the UUID is identical.

**Human feedback loop.** Open WebUI stores thumbs-up/down in `annotation.rating` on each message internally — it does NOT fire the external webhook URL for in-chat ratings. `scripts/sync_feedback.py` polls the Open WebUI API, finds rated messages, and correlates each to a Langfuse trace by `metadata.message_id` (exact, injected by the Filter Function) with a question-text + timestamp fallback for older traces. Scores are written via direct `POST /api/public/scores` to preserve `configId` (the SDK batch ingestion endpoint silently drops it). Two scores per rated message: `user_feedback` (BOOLEAN, 1=thumbs-up / 0=thumbs-down) and `user_feedback_rating` (NUMERIC, 1–10 from `annotation.details.rating` if present). State in `.sync_feedback_state.json`. The combined worker runs this automatically every 120s. The `POST /webhook` endpoint remains as a direct-call fallback.

**Online (continuous) evaluation.** `scripts/online_eval_worker.py` polls Langfuse every N seconds for new `RunnableSequence` traces (user RAG queries) and runs three code-based evaluators — `has_source_citation`, `is_within_length`, `contains_no_hallucination_markers` — pushing scores back as `online_has_citation`, `online_within_length`, `online_no_hallucination_markers` (all `BOOLEAN`). Open WebUI internal system calls (`### Task:` prefix) are filtered out. State is persisted in `.online_eval_state.json`; `--reset` clears it. Run continuously with `python -m scripts.online_eval_worker` or single-pass with `--once`. Automated via the combined worker (60s interval).

**Automated dataset building from user feedback.** `scripts/build_dataset.py` queries Langfuse for all `user_feedback=1.0` scores, fetches the linked traces, and upserts them into the `rag-golden-set` dataset as `{question, answer}` pairs with `source_trace_id` back-links. This turns every thumbs-up into a labeled gold example for experiments and regression testing — no manual curation needed. State in `.build_dataset_state.json`. The combined worker runs this every 300s. Run manually with `python -m scripts.build_dataset` (supports `--dry-run`, `--reset`, `--dataset`).

**Langfuse Prompt Management.** The RAG system prompt is stored in the Langfuse Prompt Registry (name: `rag-system-prompt`, type: chat). `app/rag/chain.py` fetches it at runtime via `langfuse.get_prompt()` with a 60 s cache and an in-process fallback (`LANGFUSE_PROMPT_MESSAGES`) if Langfuse is unreachable. Seed the prompt once with `python -m scripts.seed_langfuse_prompt`; push a new version after editing with `--force`. This lets you iterate on the prompt via the Langfuse UI without redeploying code — edit, save, the next request picks it up within 60 s.

**OpenTelemetry pipeline.** Two trace pipelines run in parallel: the Langfuse SDK (`CallbackHandler`) for LLM-native tracing (token counts, prompt/completion capture) and OTel for the full request lifecycle (HTTP ingress, httpx outbound calls, Qdrant queries). The app sends OTLP/HTTP to an `otel-collector` service, which fans out to Jaeger (UI: `:16686`) and Langfuse's OTel ingestion endpoint (`/api/public/otel`). Each request's OTel trace ID is injected into Langfuse trace metadata (`otel_trace_id`) so both systems are cross-navigable. Auto-instruments FastAPI and httpx via `opentelemetry-instrumentation-fastapi` / `opentelemetry-instrumentation-httpx`. Set `OTEL_ENABLED=false` in `.env` to disable. Auth to Langfuse uses `LANGFUSE_OTEL_AUTH` env var (Basic auth, base64 of public_key:secret_key); default matches dev keys.

## Key files

- `docker-compose.yml` - 14 services + 2 init containers. Uses YAML anchors for DRY logging/resource config. Langfuse v3 needs postgres + clickhouse + redis + minio. Ollama has GPU reservation (4 CPU, 8 GB mem). All services on a custom `langfuse` bridge network. Redis host port is 6300 (not 6379) due to Windows Hyper-V port exclusions. Postgres host port is 5500 (not 5432) — ports 5358–5457 are reserved by Hyper-V on this machine. All containers run `TZ: UTC` to prevent Langfuse from writing `createdAt`/`timestamp` in local time; without this, Langfuse v3 stores local time tagged as UTC (`Z`), making the `latency` field and all trace timestamps wrong by the UTC offset. Redis requires a password (`REDIS_PASSWORD` from `.env`); Langfuse authenticates via `REDIS_AUTH`. MinIO credentials are passed to Langfuse via `LANGFUSE_S3_*_ACCESS_KEY_ID` / `SECRET_ACCESS_KEY` env vars. A `minio-init` container auto-creates the `langfuse` bucket on first boot.
- `litellm_config.yaml` - Model routing + guardrail registration. Ollama models use `http://ollama:11434` (Docker internal). OpenRouter models use `model: openai/<provider>/<model-id>` + `api_base: https://openrouter.ai/api/v1` (the `openai/` prefix routes to OpenAI-compatible provider, which strips it and sends the bare model ID to OpenRouter — works for any model regardless of whether LiteLLM has it in its registry). Two guardrails (`prompt-injection`, `pii-masking`) are `default_on: true`.
- `guardrails/custom_guardrails.py` - LiteLLM custom guardrails. `PromptInjectionGuard` (pre_call, 12 regex patterns) blocks injection attempts including role hijacking, jailbreaks, and system prompt exfiltration. `PIIMaskingGuard` (post_call) redacts email, SSN, credit card, and phone from responses. Mounted into LiteLLM container at `/app/custom_guardrails.py`.
- `app/core/config.py` - Single source of truth for all settings (`Settings` + `settings` singleton). Compatibility shim at `app/config.py` re-exports via `*`.
- `app/core/tracing.py` - Langfuse client singleton + `CallbackHandler` factory. `get_langfuse_client()` returns the singleton (configured with `timeout=60`); `get_langfuse_handler()` returns a handler that looks up the client by public_key. Compatibility shim at `app/tracing.py`.
- `app/core/telemetry.py` - OTel SDK bootstrap. `init_telemetry(app)` sets up `TracerProvider`, `OTLPSpanExporter` (HTTP to Collector), and auto-instruments FastAPI + httpx. `get_otel_trace_id()` returns the active OTel trace ID for cross-linking into Langfuse metadata. Called from the FastAPI lifespan in `app/api/app.py`. Compatibility shim at `app/telemetry.py`.
- `app/core/logging.py` - `configure_logging(level)` wraps `logging.basicConfig` with a standard format. Called once from `app/cli/app.py::main()` before command dispatch.
- `app/core/ids.py` - `request_id()` (12-char hex, for log correlation) and `completion_id()` (OpenAI-style `chatcmpl-<hex8>`).
- `app/main.py` - Bare entry point: `from app.cli.app import main` + `if __name__ == "__main__": main()`.
- `app/cli/app.py` - Argument parser and dispatch. `_build_parser()` calls each command module's `register(sub)`; `main()` calls `configure_logging()` then dispatches via `args.func(args)`.
- `app/cli/commands/` - One module per command domain: `ingest.py`, `query.py`, `agent.py`, `evaluate.py`, `experiment.py`, `dataset.py`, `regression.py`, `benchmark.py`. Each exposes `register(sub)` and command functions. All call through domain service wrappers.
- `app/api/__init__.py` - Lazy-loads the FastAPI `app` object via `__getattr__` so importing `app.api.services.*` does not require fastapi. `uvicorn app.api:app` still works.
- `app/api/app.py` - `create_app()` factory: builds FastAPI app, registers CORS middleware and all routers, sets up OTel in lifespan.
- `app/api/schemas.py` - `Message` and `ChatRequest` Pydantic models.
- `app/api/streaming.py` - `stream_from_result()` SSE generator.
- `app/api/routes/` - Thin handlers: `health.py`, `models.py`, `webhook.py`, `chat.py`. Each validates the request, calls one service function, returns the result.
- `app/api/services/models_service.py` - `MODELS`, `DIRECT_MODELS`, model descriptions, `get_model_list()`. Canonical location for virtual-model config (imported by `chat_service`).
- `app/api/services/health_service.py` - `_probe(name, url)` async prober + `check_all()` aggregator.
- `app/api/services/feedback_service.py` - `parse_feedback(payload)` normalises flat/nested Open WebUI payloads; `push_score()` writes to Langfuse; `handle_webhook()` orchestrates the full flow.
- `app/api/services/direct_llm.py` - Direct LiteLLM call (no RAG). All httpx errors caught and returned as inline error strings.
- `app/api/services/rag_llm.py` - RAG chain invocation via `rag_service.build_chain()`. Uses Langfuse trace ID as the completion ID for feedback correlation.
- `app/api/services/chat_service.py` - Dispatch orchestrator: picks direct vs. RAG path, annotates OTel span, builds the OpenAI-format completion response.
- `app/rag/ingest.py` - Loads documents from the local corpus (`mock_corpus/` by default) recursively. `.md` files load as-is; `.jsonl` files are split into one Document per line with records rendered as readable `key: value` text. Chunks with `RecursiveCharacterTextSplitter`, embeds via LiteLLM, stores in Qdrant. Detects embedding dimension automatically. No web scraping.
- `app/rag/chain.py` - LCEL chain internals. `ScoredRetriever(BaseRetriever)` calls `similarity_search_with_score()`, injects `retrieval_score` into doc metadata, and sets four OTel span attributes. `build_rag_chain(guardrails_enabled=True)` wires retriever → prompt → LLM → parser. Pass `guardrails_enabled=False` to disable LiteLLM guardrails for that request via `extra_body` (used by the benchmark runner for ablation comparisons).
- `app/rag/service.py` - Stable domain interface: `ingest()`, `query()`, `build_chain()`. CLI commands and the API service layer call this instead of the chain/ingest modules directly.
- `app/agent/tools.py` - Five `@tool` functions: `search_docs`, `list_traces`, `get_trace_detail`, `score_response`, `get_dataset_summary`. Each reuses existing infrastructure (retriever, Langfuse client, evaluators).
- `app/agent/graph.py` - LangGraph ReAct agent. `build_agent(model, checkpointer)` returns a compiled graph. `run_agent(question, ...)` is the main entry point. Trace shape differs from the RAG chain: each reasoning iteration creates a `ChatOpenAI` observation; tool executions sit between them as `tools` → `<tool_name>` observations. A 3-tool query produces 4 `ChatOpenAI` spans and 3 `tools` nodes under a `LangGraph` root. In Jaeger, this appears as N sequential `POST /v1/chat/completions` httpx spans (one per LLM round-trip) — the count is the fingerprint of an agentic trace vs. a single-shot RAG trace.
- `app/agent/prompts.py` - Agent system prompt.
- `app/agent/service.py` - Stable domain interface: `run()`, `build_chat_session()`, `respond()`. Encapsulates `MemorySaver` + `HumanMessage` so CLI and API don't depend on LangGraph internals.
- `app/eval/evaluators.py` - Four code-based evaluators + one LLM-as-judge. The judge returns JSON with binary relevance/faithfulness/completeness scores.
- `app/eval/deepeval_metrics.py` - `LiteLLMModel(DeepEvalBaseLLM)` routes judge calls through LiteLLM. Metric factory functions + `METRIC_REGISTRY` for dynamic lookup.
- `app/eval/deepeval_runner.py` - `run_deepeval_evaluation()` fetches a Langfuse dataset, runs the RAG chain, evaluates with DeepEval, pushes scores to Langfuse.
- `app/eval/experiments.py` - Multi-model experiment runner. `run_experiment(dataset, models)` runs every model against every dataset item, scores with DeepEval, pushes scores to Langfuse, and links each trace to a named dataset run via `client.api.dataset_run_items.create()`. `print_comparison_table()` prints a per-model average score table using ASCII box chars (Unicode box-drawing chars fail on Windows cp1252). `LLMTestCase` passes `context=retrieval_context` (required by `HallucinationMetric`) in addition to `retrieval_context`.
- `app/eval/service.py` - Stable domain interface: `evaluate()`, `experiment()`, `show_experiment_table()`, `regression_gate()`. CLI commands call this instead of the runner/experiment modules or scripts directly.
- `app/eval/benchmark.py` - Benchmark runner for the NorthstarCRM knowledge base. Evaluates the RAG pipeline across five metrics: retrieval hit rate, factual coverage, policy violation rate, correct escalation rate, answer helpfulness. Supports three run modes: `full` (RAG + guardrails), `no-guardrails` (RAG, guardrails off via `extra_body`), `direct` (bare LLM, no retrieval). Loads items from `mock_corpus/07_benchmark/` (JSONL). `run_benchmark()` drives item × mode combinations; `print_results()` outputs per-question details and an aggregate comparison table. Code-based metrics: `eval_retrieval_hit` (filename or full-path match), `eval_factual_coverage` (stop-word-filtered token overlap), `eval_escalation` (15 escalation-intent phrases). LLM-as-judge metrics: `eval_policy_violation` (7 NorthstarCRM sales policies + scoring rules that distinguish correct refusals from true violations), `eval_helpfulness` (1–5 deal-progression score). `_parse_judge_json()` strips markdown fences before parsing judge responses. CLI flag `--item <id>` (e.g. `--item edge_002`) runs a single benchmark item; combine with `--compare` to see all three modes for that item.
- `scripts/build_dataset.py` - Builds the `rag-golden-set` Langfuse dataset from positively rated traces. Queries `user_feedback=1.0` scores, fetches each linked trace, upserts `{question, answer}` items with `source_trace_id`. `run_once()` is called by the worker every 5 minutes. State in `.build_dataset_state.json`.
- `scripts/regression_gate.py` - `run_gate()` implements the quality gate logic (run dataset items through RAG, evaluate with DeepEval, check thresholds). Exit codes: 0=all pass, 1=metric failure, 2=runtime error. Default thresholds: `FaithfulnessMetric≥0.80`, `AnswerRelevancyMetric≥0.70`, `ContextualRelevancyMetric≥0.30`, `HallucinationMetric≤0.30`. `HallucinationMetric` is lower-is-better — threshold is a maximum, not a minimum. Override thresholds via `--thresholds '{"FaithfulnessMetric":0.85}'`. Called by `app/eval/service.py::regression_gate()` and also callable directly: `python -m scripts.regression_gate --limit 5`.
- `scripts/worker.py` - Combined background daemon. Runs three pollers in threads: `eval-worker` (60s), `feedback-worker` (120s), `dataset-builder` (300s). Seeds score configs on startup. Launched automatically by the `agentguard-worker` Docker service.
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

# One-time setup (after first docker compose up):
python -m scripts.seed_langfuse_prompt        # Register RAG system prompt in Langfuse
python -m scripts.seed_langfuse_prompt --force # Push a new version (after editing)

# Background workers (run automatically by agentguard-worker Docker service):
python -m scripts.worker               # All three pollers in one process
python -m scripts.online_eval_worker --once   # Single eval pass
python -m scripts.sync_feedback --apply       # Single feedback sync pass
python -m scripts.build_dataset               # Build/update rag-golden-set dataset
python -m scripts.build_dataset --dry-run     # Preview without writing
python -m scripts.build_dataset --reset       # Rebuild from scratch
```

### Adding a new model

Add an entry to `litellm_config.yaml` under `model_list`, then use the `model_name` value with `--model`:

```bash
python -m app.main query "question" --model new-model-name
```

### Adding a new evaluator

Add a function to `app/eval/evaluators.py` that takes the output string and returns a score. Then wire it into `run_experiment()` in `app/eval/experiments.py` inside the `scores` dict. For DeepEval metrics, add a factory function to `app/eval/deepeval_metrics.py` and register it in `METRIC_REGISTRY`.

### Adding a new agent tool

Add a `@tool`-decorated function to `app/agent/tools.py` with a clear docstring (the LLM reads it to decide when to use the tool). Add it to the `ALL_TOOLS` list. Update the system prompt in `app/agent/prompts.py` to mention the new tool.

### Tracing

Every function that calls an LLM should accept a `callbacks` parameter and pass it to LangChain's `.invoke(config={"callbacks": callbacks})`. CLI commands obtain the handler via `get_langfuse_handler()` (from `app/core/tracing.py`) and pass it to the domain service functions.

### Tests

```bash
pytest -m "not integration"   # 263 unit tests, no Docker needed (~5s)
pytest -m integration          # 17 integration tests, Docker stack must be running
pytest -v                      # Full suite
```

Integration tests auto-skip if the Docker stack is unreachable (checks `localhost:4000/health/liveliness` in `conftest.py`). The guardrail tests mock the entire `litellm` module hierarchy via `sys.modules` because `litellm` only exists inside the Docker container. `app/api/__init__.py` uses `__getattr__` lazy-loading so importing `app.api.services.*` in unit tests does not require fastapi.

### Guardrails

Two LiteLLM custom guardrails run on every request by default:
- **Prompt injection** (pre_call): blocks 12 regex patterns (jailbreak, ignore instructions, DAN, system prompt exfiltration, etc.). The DAN pattern uses `(?-i:DAN)\b` for case-sensitive matching to avoid false-positiving on the name "Dan". The system prompt pattern catches `give/show/reveal/print/display/output/repeat/tell ... system prompt/instructions/rules`. Raises `litellm.exceptions.BadRequestError` so LiteLLM returns HTTP 400 — not a plain `ValueError` (which maps to 500 and is indistinguishable from a model error).
- **PII masking** (post_call): redacts email, SSN, credit card, phone from LLM responses using regex.

Guardrails config: the `guardrails:` key in `litellm_config.yaml` is **top-level** — do not nest it under `litellm_settings:`. The module name in `guardrail:` must match the mounted filename (`custom_guardrails`, not `custom_guardrail`).

To test guardrails manually, see `VALIDATION.md` section 8.

### Docker networking

Services reference each other by container name (`postgres`, `redis`, `ollama`, `minio`, etc.) on the `langfuse` bridge network. The app code runs on the host and uses `localhost` ports. If you move the app into Docker, change `app/core/config.py` defaults or `.env` values to use container names.

### Docker resource management

All containers have log rotation (`10m` max, 2 files). Memory-heavy services have explicit CPU/memory limits via YAML anchors (`x-deploy-clickhouse`, `x-deploy-postgres`, `x-deploy-ollama`). Total Docker memory budget is ~15 GB. Portainer (`:9443`) provides container management UI; Dozzle (`:8080`) provides real-time log streaming.

### Environment

- Python 3.11+
- Windows 11 (port 6379 is blocked by Hyper-V, so Redis maps to 6300)
- `.env` is gitignored; copy from `.env.example`
- The `data/docs/` directory is gitignored for any local markdown files used during ingestion

## Known issues

- **LiteLLM image (`ghcr.io/berriai/litellm:main-latest`)** requires a PostgreSQL database. The compose gives it a `DATABASE_URL` env var pointing to a `litellm` database on the shared Postgres instance. On first boot, Prisma migrations run automatically (~30s). The `master_key` in `litellm_config.yaml` must be a literal string (not an env var reference) so it registers correctly in the DB. LiteLLM UI login uses `UI_USERNAME` / `UI_PASSWORD` env vars (defaults: `admin` / `litellm123456`) — not the master key.
- **Langfuse SDK v4** removed `fetch_traces`, `fetch_trace`, and `fetch_datasets`. Agent tools use the new `client.api` namespace: `client.api.trace.list(limit=N)` returns `response.data`; `client.api.trace.get(trace_id)` returns the trace directly (no `.data` wrapper); `client.api.datasets.list()` returns `response.data`. See `app/agent/tools.py`.
- **Langfuse SDK v4** also changed the `CallbackHandler` interface. It no longer accepts `session_id`, `tags`, or `metadata` kwargs — use `trace_context` or let the handler look up the client singleton by `public_key`. See `app/core/tracing.py`.
- Ollama serves only the embedding model. Pull it manually after first `docker compose up`: `docker compose exec ollama ollama pull nomic-embed-text`. All chat LLM calls go through OpenRouter via LiteLLM.
- The `ingest` command uses `force_recreate=True` on the Qdrant collection, so re-running it wipes and rebuilds the entire index. The `QdrantClient` and `QdrantVectorStore.from_documents` both use `timeout=120` to handle slow collection operations under resource pressure.
- **Default model is `openrouter-gemini-flash`.** Both chat generation and DeepEval judge calls use this model by default. Override with `--model openrouter-mistral` or set `DEFAULT_MODEL` / `DEEPEVAL_MODEL` in `.env`.
- **MinIO S3 credentials must be passed to Langfuse.** Langfuse v3 uses S3-compatible storage (MinIO) for event and media uploads. Without `LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID` / `SECRET_ACCESS_KEY` in the Langfuse environment, the AWS SDK falls back to instance metadata and fails with "Could not load credentials from any providers", causing span export errors ("Transient error Internal Server Error"). The docker-compose references `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` from `.env`.
- **MinIO `langfuse` bucket must exist.** The `minio-init` container creates it automatically. If you see S3 upload errors after wiping volumes, check the bucket exists: `docker exec <minio-container> mc alias set local http://localhost:9000 minio miniosecret && mc ls local/langfuse`.
- **Redis requires a password.** The Redis container is started with `--requirepass` using `REDIS_PASSWORD` from `.env`. Langfuse authenticates via `REDIS_AUTH`. If `.env` has a `REDIS_PASSWORD` but Redis isn't configured to require it, the worker logs "ERR AUTH called without any password configured" warnings.
- **langfuse-worker Redis socket timeout errors are expected.** `@langfuse/shared` hardcodes `socketTimeout: 30000` on all ioredis connections (comment: "prevents hung moveToCompleted() from blocking concurrency slots forever"). This fires every ~30s on idle BullMQ connections. The `REDIS_SOCKET_TIMEOUT_MS` env var is ignored in this build — the value is not read by BullMQ's connection path. BullMQ auto-reconnects after each timeout; the worker remains healthy and jobs are not lost. The error spam is cosmetic.
- **All outbound HTTP calls use a 60s timeout.** The Langfuse SDK client (`app/core/tracing.py`) and all `httpx` calls in `scripts/` use `timeout=60` to tolerate slow responses from a resource-constrained local Docker stack. Increase if you see timeouts on very slow hardware.
