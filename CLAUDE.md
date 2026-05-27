# CLAUDE.md - AgentGuard

## What this project is

AgentGuard — "The QA layer for agentic AI that everybody loves to ignore."

A self-hosted RAG application with observability, guardrails, and evaluation built in. It answers questions about Langfuse documentation and uses Langfuse to observe itself doing it. Demonstrates the full AI Engineering Loop: Trace -> Monitor -> Datasets -> Experiment -> Evaluate.

## Architecture decisions

**LiteLLM as a unified proxy.** All LLM calls (chat + embeddings) go through `http://localhost:4000`, which routes to Ollama locally or OpenRouter for cloud fallback. The app never talks to Ollama directly - it always uses the OpenAI-compatible API from LiteLLM. This means swapping or adding models is a config change in `litellm_config.yaml`, not a code change.

**LangChain LCEL for the RAG chain.** The chain in `app/rag/chain.py` is a simple pipe: retriever | format_docs -> prompt -> llm -> StrOutputParser. LangChain was chosen because the Langfuse `CallbackHandler` integrates natively with it, giving automatic tracing of every step without manual instrumentation.

**LangGraph ReAct agent.** The agent in `app/agent/graph.py` is a `StateGraph(MessagesState)` with two nodes: `agent` (LLM with bound tools) and `tools` (ToolNode). The agent decides which tools to call based on the question. Five tools are available: doc search, trace listing, trace detail, response scoring, and dataset summary. The Langfuse CallbackHandler traces every node automatically. `MemorySaver` provides multi-turn memory for chat sessions.

**DeepEval for LLM-judged evaluation.** DeepEval metrics (faithfulness, answer relevancy, contextual relevancy, hallucination) run through a `LiteLLMModel` wrapper that routes judge calls through the same LiteLLM proxy. Scores are pushed back to Langfuse via `client.create_score()`. This replaces the need for the hand-rolled LLM-as-judge for most use cases.

**Qdrant for vector storage.** Chosen over Chroma/FAISS because it runs as a proper service in Docker with persistence, has a good LangChain integration, and provides both HTTP and gRPC APIs.

**Pydantic Settings for config.** `app/config.py` loads from `.env` with sensible defaults. Every external URL and credential is configurable. The `settings` singleton is imported everywhere.

**Langfuse auto-provisioning.** The docker-compose uses `LANGFUSE_INIT_*` env vars to create a default org, project, and API keys on first boot. No manual setup needed - keys `pk-lf-dev` / `sk-lf-dev` work immediately.

**Open WebUI → Langfuse session linking.** Session linking requires a Filter Function installed in Open WebUI (Admin → Functions) — import from `config/openwebui/chat_id_injection.json` (fastest) or paste `scripts/openwebui_langfuse_filter.py` manually. See SHOWCASE.md §5.0. Open WebUI build `3660bc00` does not send a `chat-id` header; instead, the filter's `inlet` method reads `__metadata__["chat_id"]` (the current conversation UUID) and injects it into the request body as `body["chat_id"]`. `app/api.py` reads `body.chat_id` (falling back to the `chat-id` header for older builds) and wraps the RAG chain with `propagate_attributes(session_id=chat_id)` from the Langfuse SDK. This stamps the Open WebUI chat UUID as `session_id` on every Langfuse trace, grouping all turns of a conversation under one Langfuse Session. Navigation: `http://localhost:3001/c/<uuid>` maps directly to `http://localhost:3000/project/my-project/sessions/<uuid>` — the UUID is identical.

**Human feedback loop.** Open WebUI stores thumbs-up/down in `annotation.rating` on each message internally — it does NOT fire the external webhook URL for in-chat ratings. `scripts/sync_feedback.py` polls the Open WebUI API, finds rated messages, and correlates each to a Langfuse trace by `metadata.message_id` (exact, injected by the Filter Function) with a question-text + timestamp fallback for older traces. Scores are written via direct `POST /api/public/scores` to preserve `configId` (the SDK batch ingestion endpoint silently drops it). Two scores per rated message: `user_feedback` (BOOLEAN, 1=thumbs-up / 0=thumbs-down) and `user_feedback_rating` (NUMERIC, 1–10 from `annotation.details.rating` if present). State in `.sync_feedback_state.json`. The combined worker runs this automatically every 120s. The `POST /webhook` endpoint remains as a direct-call fallback.

**Online (continuous) evaluation.** `scripts/online_eval_worker.py` polls Langfuse every N seconds for new `RunnableSequence` traces (user RAG queries) and runs three code-based evaluators — `has_source_citation`, `is_within_length`, `contains_no_hallucination_markers` — pushing scores back as `online_has_citation`, `online_within_length`, `online_no_hallucination_markers` (all `BOOLEAN`). Open WebUI internal system calls (`### Task:` prefix) are filtered out. State is persisted in `.online_eval_state.json`; `--reset` clears it. Run continuously with `python -m scripts.online_eval_worker` or single-pass with `--once`. Automated via the combined worker (60s interval).

**Automated dataset building from user feedback.** `scripts/build_dataset.py` queries Langfuse for all `user_feedback=1.0` scores, fetches the linked traces, and upserts them into the `rag-golden-set` dataset as `{question, answer}` pairs with `source_trace_id` back-links. This turns every thumbs-up into a labeled gold example for experiments and regression testing — no manual curation needed. State in `.build_dataset_state.json`. The combined worker runs this every 300s. Run manually with `python -m scripts.build_dataset` (supports `--dry-run`, `--reset`, `--dataset`).

**Langfuse Prompt Management.** The RAG system prompt is stored in the Langfuse Prompt Registry (name: `rag-system-prompt`, type: chat). `app/rag/chain.py` fetches it at runtime via `langfuse.get_prompt()` with a 60 s cache and an in-process fallback (`LANGFUSE_PROMPT_MESSAGES`) if Langfuse is unreachable. Seed the prompt once with `python -m scripts.seed_langfuse_prompt`; push a new version after editing with `--force`. This lets you iterate on the prompt via the Langfuse UI without redeploying code — edit, save, the next request picks it up within 60 s.

**OpenTelemetry pipeline.** Two trace pipelines run in parallel: the Langfuse SDK (`CallbackHandler`) for LLM-native tracing (token counts, prompt/completion capture) and OTel for the full request lifecycle (HTTP ingress, httpx outbound calls, Qdrant queries). The app sends OTLP/HTTP to an `otel-collector` service, which fans out to Jaeger (UI: `:16686`) and Langfuse's OTel ingestion endpoint (`/api/public/otel`). Each request's OTel trace ID is injected into Langfuse trace metadata (`otel_trace_id`) so both systems are cross-navigable. Auto-instruments FastAPI and httpx via `opentelemetry-instrumentation-fastapi` / `opentelemetry-instrumentation-httpx`. Set `OTEL_ENABLED=false` in `.env` to disable. Auth to Langfuse uses `LANGFUSE_OTEL_AUTH` env var (Basic auth, base64 of public_key:secret_key); default matches dev keys.

## Key files

- `docker-compose.yml` - 14 services + 2 init containers. Uses YAML anchors for DRY logging/resource config. Langfuse v3 needs postgres + clickhouse + redis + minio. Ollama has GPU reservation (4 CPU, 8 GB mem). All services on a custom `langfuse` bridge network. Redis host port is 6300 (not 6379) due to Windows port conflicts. Redis requires a password (`REDIS_PASSWORD` from `.env`); Langfuse authenticates via `REDIS_AUTH`. MinIO credentials are passed to Langfuse via `LANGFUSE_S3_*_ACCESS_KEY_ID` / `SECRET_ACCESS_KEY` env vars. A `minio-init` container auto-creates the `langfuse` bucket on first boot.
- `litellm_config.yaml` - Model routing + guardrail registration. Ollama models use `http://ollama:11434` (Docker internal). OpenRouter models use `model: openai/<provider>/<model-id>` + `api_base: https://openrouter.ai/api/v1` (the `openai/` prefix routes to OpenAI-compatible provider, which strips it and sends the bare model ID to OpenRouter — works for any model regardless of whether LiteLLM has it in its registry). Two guardrails (`prompt-injection`, `pii-masking`) are `default_on: true`.
- `guardrails/custom_guardrails.py` - LiteLLM custom guardrails. `PromptInjectionGuard` (pre_call, 12 regex patterns) blocks injection attempts including role hijacking, jailbreaks, and system prompt exfiltration. `PIIMaskingGuard` (post_call) redacts email, SSN, credit card, and phone from responses. Mounted into LiteLLM container at `/app/custom_guardrails.py`.
- `app/config.py` - Single source of truth for all settings.
- `app/tracing.py` - Langfuse client singleton + `CallbackHandler` factory. `get_langfuse_client()` returns the singleton (configured with `timeout=60`); `get_langfuse_handler()` returns a handler that looks up the client by public_key.
- `app/rag/ingest.py` - Scrapes Langfuse Academy URLs, chunks with `RecursiveCharacterTextSplitter`, embeds via LiteLLM, stores in Qdrant. Detects embedding dimension automatically.
- `app/rag/chain.py` - LCEL chain. `query()` is the main entry point.
- `app/api.py` - OpenAI-compatible FastAPI wrapper. Three virtual models: `agentguard-rag` / `agentguard-rag-mistral` route through the RAG chain; `agentguard-direct` bypasses RAG and calls LiteLLM directly (no context-only constraint — useful for guardrail demos). All three go through LiteLLM so injection guard and PII masking apply everywhere.
- `app/agent/tools.py` - Five `@tool` functions: `search_docs`, `list_traces`, `get_trace_detail`, `score_response`, `get_dataset_summary`. Each reuses existing infrastructure (retriever, Langfuse client, evaluators).
- `app/agent/graph.py` - LangGraph ReAct agent. `build_agent(model, checkpointer)` returns a compiled graph. `run_agent(question, ...)` is the main entry point.
- `app/agent/prompts.py` - Agent system prompt.
- `app/eval/evaluators.py` - Four code-based evaluators + one LLM-as-judge. The judge returns JSON with binary relevance/faithfulness/completeness scores.
- `app/eval/deepeval_metrics.py` - `LiteLLMModel(DeepEvalBaseLLM)` routes judge calls through LiteLLM. Metric factory functions + `METRIC_REGISTRY` for dynamic lookup.
- `app/eval/deepeval_runner.py` - `run_deepeval_evaluation()` fetches a Langfuse dataset, runs the RAG chain, evaluates with DeepEval, pushes scores to Langfuse.
- `app/eval/experiments.py` - Multi-model experiment runner. `run_experiment(dataset, models)` runs every model against every dataset item, scores with DeepEval, pushes scores to Langfuse, and links each trace to a named dataset run via `client.api.dataset_run_items.create()`. `print_comparison_table()` prints a per-model average score table. CLI: `python -m app.main experiment --dataset rag-golden-set --models m1,m2`.
- `scripts/build_dataset.py` - Builds the `rag-golden-set` Langfuse dataset from positively rated traces. Queries `user_feedback=1.0` scores, fetches each linked trace, upserts `{question, answer}` items with `source_trace_id`. `run_once()` is called by the worker every 5 minutes. State in `.build_dataset_state.json`.
- `scripts/worker.py` - Combined background daemon. Runs three pollers in threads: `eval-worker` (60s), `feedback-worker` (120s), `dataset-builder` (300s). Seeds score configs on startup. Launched automatically by the `agentguard-worker` Docker service.
- `scripts/utils.py` - Shared utilities for scripts: `langfuse_basic_auth()`, `load_state()`/`save_state()` (corrupt-safe JSON state files), `HTTP_TIMEOUT`, `TRACE_PAGE_SIZE`, `SCORE_PAGE_SIZE`.
- `app/utils.py` - Shared app-layer utilities: `truncate(text, max_len)`, `extract_trace_output(trace)` (normalises None/str/dict trace output to plain string).
- `app/telemetry.py` - OTel SDK bootstrap. `init_telemetry(app)` sets up `TracerProvider`, `OTLPSpanExporter` (HTTP to Collector), and auto-instruments FastAPI + httpx. `get_otel_trace_id()` returns the active OTel trace ID for cross-linking into Langfuse metadata. Called from the FastAPI lifespan in `app/api.py`.
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

Every function that calls an LLM should accept a `callbacks` parameter and pass it to LangChain's `.invoke(config={"callbacks": callbacks})`. The CLI creates the handler in `app/main.py` and threads it through.

### Tests

```bash
pytest -m "not integration"   # 135 unit tests, no Docker needed (~9s)
pytest -m integration          # 17 integration tests, Docker stack must be running
pytest -v                      # Full suite
```

Integration tests auto-skip if the Docker stack is unreachable (checks `localhost:4000/health/liveliness` in `conftest.py`). The guardrail tests mock the entire `litellm` module hierarchy via `sys.modules` because `litellm` only exists inside the Docker container.

### Guardrails

Two LiteLLM custom guardrails run on every request by default:
- **Prompt injection** (pre_call): blocks 12 regex patterns (jailbreak, ignore instructions, DAN, system prompt exfiltration, etc.). The DAN pattern uses `(?-i:DAN)\b` for case-sensitive matching to avoid false-positiving on the name "Dan". The system prompt pattern catches `give/show/reveal/print/display/output/repeat/tell ... system prompt/instructions/rules`. Raises `litellm.exceptions.BadRequestError` so LiteLLM returns HTTP 400 — not a plain `ValueError` (which maps to 500 and is indistinguishable from a model error).
- **PII masking** (post_call): redacts email, SSN, credit card, phone from LLM responses using regex.

Guardrails config: the `guardrails:` key in `litellm_config.yaml` is **top-level** — do not nest it under `litellm_settings:`. The module name in `guardrail:` must match the mounted filename (`custom_guardrails`, not `custom_guardrail`).

To test guardrails manually, see `VALIDATION.md` section 8.

### Docker networking

Services reference each other by container name (`postgres`, `redis`, `ollama`, `minio`, etc.) on the `langfuse` bridge network. The app code runs on the host and uses `localhost` ports. If you move the app into Docker, change `app/config.py` defaults or `.env` values to use container names.

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
- **Langfuse SDK v4** also changed the `CallbackHandler` interface. It no longer accepts `session_id`, `tags`, or `metadata` kwargs — use `trace_context` or let the handler look up the client singleton by `public_key`. See `app/tracing.py`.
- Ollama serves only the embedding model. Pull it manually after first `docker compose up`: `docker compose exec ollama ollama pull nomic-embed-text`. All chat LLM calls go through OpenRouter via LiteLLM.
- The `ingest` command uses `force_recreate=True` on the Qdrant collection, so re-running it wipes and rebuilds the entire index. The `QdrantClient` and `QdrantVectorStore.from_documents` both use `timeout=120` to handle slow collection operations under resource pressure.
- **Default model is `openrouter-gemini-flash`.** Both chat generation and DeepEval judge calls use this model by default. Override with `--model openrouter-mistral` or set `DEFAULT_MODEL` / `DEEPEVAL_MODEL` in `.env`.
- **MinIO S3 credentials must be passed to Langfuse.** Langfuse v3 uses S3-compatible storage (MinIO) for event and media uploads. Without `LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID` / `SECRET_ACCESS_KEY` in the Langfuse environment, the AWS SDK falls back to instance metadata and fails with "Could not load credentials from any providers", causing span export errors ("Transient error Internal Server Error"). The docker-compose references `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` from `.env`.
- **MinIO `langfuse` bucket must exist.** The `minio-init` container creates it automatically. If you see S3 upload errors after wiping volumes, check the bucket exists: `docker exec <minio-container> mc alias set local http://localhost:9000 minio miniosecret && mc ls local/langfuse`.
- **Redis requires a password.** The Redis container is started with `--requirepass` using `REDIS_PASSWORD` from `.env`. Langfuse authenticates via `REDIS_AUTH`. If `.env` has a `REDIS_PASSWORD` but Redis isn't configured to require it, the worker logs "ERR AUTH called without any password configured" warnings.
- **langfuse-worker Redis socket timeout errors are expected.** `@langfuse/shared` hardcodes `socketTimeout: 30000` on all ioredis connections (comment: "prevents hung moveToCompleted() from blocking concurrency slots forever"). This fires every ~30s on idle BullMQ connections. The `REDIS_SOCKET_TIMEOUT_MS` env var is ignored in this build — the value is not read by BullMQ's connection path. BullMQ auto-reconnects after each timeout; the worker remains healthy and jobs are not lost. The error spam is cosmetic.
- **All outbound HTTP calls use a 60s timeout.** The Langfuse SDK client (`app/tracing.py`) and all `httpx` calls in `scripts/` use `timeout=60` to tolerate slow responses from a resource-constrained local Docker stack. Increase if you see timeouts on very slow hardware.
