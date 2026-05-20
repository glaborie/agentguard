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

## Key files

- `docker-compose.yml` - 11 services. Uses YAML anchors for DRY logging/resource config. Langfuse v3 needs postgres + clickhouse + redis + minio. Ollama has GPU reservation (4 CPU, 8 GB mem). All services on a custom `langfuse` bridge network. Redis host port is 6300 (not 6379) due to Windows port conflicts.
- `litellm_config.yaml` - Model routing + guardrail registration. Ollama models use `http://ollama:11434` (Docker internal). OpenRouter models use env var for API key. Two guardrails (`prompt-injection`, `pii-masking`) are `default_on: true`.
- `guardrails/custom_guardrails.py` - LiteLLM custom guardrails. `PromptInjectionGuard` (pre_call, 12 regex patterns) blocks injection attempts including role hijacking, jailbreaks, and system prompt exfiltration. `PIIMaskingGuard` (post_call) redacts email, SSN, credit card, and phone from responses. Mounted into LiteLLM container at `/app/custom_guardrails.py`.
- `app/config.py` - Single source of truth for all settings.
- `app/tracing.py` - Langfuse client singleton + `CallbackHandler` factory. `get_langfuse_client()` returns the singleton; `get_langfuse_handler()` returns a handler that looks up the client by public_key.
- `app/rag/ingest.py` - Scrapes Langfuse Academy URLs, chunks with `RecursiveCharacterTextSplitter`, embeds via LiteLLM, stores in Qdrant. Detects embedding dimension automatically.
- `app/rag/chain.py` - LCEL chain. `query()` is the main entry point.
- `app/agent/tools.py` - Five `@tool` functions: `search_docs`, `list_traces`, `get_trace_detail`, `score_response`, `get_dataset_summary`. Each reuses existing infrastructure (retriever, Langfuse client, evaluators).
- `app/agent/graph.py` - LangGraph ReAct agent. `build_agent(model, checkpointer)` returns a compiled graph. `run_agent(question, ...)` is the main entry point.
- `app/agent/prompts.py` - Agent system prompt.
- `app/eval/evaluators.py` - Four code-based evaluators + one LLM-as-judge. The judge returns JSON with binary relevance/faithfulness/completeness scores.
- `app/eval/deepeval_metrics.py` - `LiteLLMModel(DeepEvalBaseLLM)` routes judge calls through LiteLLM. Metric factory functions + `METRIC_REGISTRY` for dynamic lookup.
- `app/eval/deepeval_runner.py` - `run_deepeval_evaluation()` fetches a Langfuse dataset, runs the RAG chain, evaluates with DeepEval, pushes scores to Langfuse.
- `app/eval/experiments.py` - Iterates dataset items x models, runs each through the RAG chain, applies code-based evaluators, returns `ExperimentResult` list.

## How to work with this codebase

### Running commands

```bash
python -m app.main ingest              # Ingest docs into Qdrant
python -m app.main query "question"    # Single RAG query with tracing
python -m app.main chat                # Interactive RAG chat
python -m app.main agent "question"    # ReAct agent with tools
python -m app.main agent-chat          # Interactive agent chat with memory
python -m app.main evaluate --dataset name  # Run DeepEval metrics
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
- **Prompt injection** (pre_call): blocks 12 regex patterns (jailbreak, ignore instructions, DAN, system prompt exfiltration, etc.). The DAN pattern uses `(?-i:DAN)\b` for case-sensitive matching to avoid false-positiving on the name "Dan". The system prompt pattern catches `give/show/reveal/print/display/output/repeat/tell ... system prompt/instructions/rules`.
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
- Ollama model pulls must be done manually after first `docker compose up` (`docker compose exec ollama ollama pull llama3.2`).
- The `ingest` command uses `force_recreate=True` on the Qdrant collection, so re-running it wipes and rebuilds the entire index. The `QdrantClient` and `QdrantVectorStore.from_documents` both use `timeout=120` to handle slow collection operations under resource pressure.
- **DeepEval judge metrics with local models.** DeepEval's LLM-judged metrics are designed for GPT-4 class models. With Ollama (llama3.2 7B), judge quality is lower. Set `DEEPEVAL_MODEL` in `.env` to an OpenRouter model for better evaluation quality.
