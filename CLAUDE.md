# CLAUDE.md - AgentGuard

## What this project is

AgentGuard — "The QA layer for agentic AI that everybody loves to ignore."

A self-hosted RAG application with observability, guardrails, and evaluation built in. It answers questions about Langfuse documentation and uses Langfuse to observe itself doing it. Demonstrates the full AI Engineering Loop: Trace -> Monitor -> Datasets -> Experiment -> Evaluate.

## Architecture decisions

**LiteLLM as a unified proxy.** All LLM calls (chat + embeddings) go through `http://localhost:4000`, which routes to Ollama locally or OpenRouter for cloud fallback. The app never talks to Ollama directly - it always uses the OpenAI-compatible API from LiteLLM. This means swapping or adding models is a config change in `litellm_config.yaml`, not a code change.

**LangChain LCEL for the RAG chain.** The chain in `app/rag/chain.py` is a simple pipe: retriever | format_docs -> prompt -> llm -> StrOutputParser. LangChain was chosen because the Langfuse `CallbackHandler` integrates natively with it, giving automatic tracing of every step without manual instrumentation.

**Qdrant for vector storage.** Chosen over Chroma/FAISS because it runs as a proper service in Docker with persistence, has a good LangChain integration, and provides both HTTP and gRPC APIs.

**Pydantic Settings for config.** `app/config.py` loads from `.env` with sensible defaults. Every external URL and credential is configurable. The `settings` singleton is imported everywhere.

**Langfuse auto-provisioning.** The docker-compose uses `LANGFUSE_INIT_*` env vars to create a default org, project, and API keys on first boot. No manual setup needed - keys `pk-lf-dev` / `sk-lf-dev` work immediately.

## Key files

- `docker-compose.yml` - 9 services. Langfuse v3 needs postgres + clickhouse + redis + minio. Ollama has GPU reservation. Redis host port is 6300 (not 6379) due to Windows port conflicts.
- `litellm_config.yaml` - Model routing. Ollama models use `http://ollama:11434` (Docker internal). OpenRouter models use env var for API key.
- `app/config.py` - Single source of truth for all settings.
- `app/tracing.py` - Factory for Langfuse `CallbackHandler`. Pass the handler as a callback to any LangChain `.invoke()` call.
- `app/rag/ingest.py` - Scrapes Langfuse Academy URLs, chunks with `RecursiveCharacterTextSplitter`, embeds via LiteLLM, stores in Qdrant. Detects embedding dimension automatically.
- `app/rag/chain.py` - LCEL chain. `query()` is the main entry point.
- `app/eval/evaluators.py` - Four code-based evaluators + one LLM-as-judge. The judge returns JSON with binary relevance/faithfulness/completeness scores.
- `app/eval/experiments.py` - Iterates dataset items x models, runs each through the RAG chain, applies evaluators, returns `ExperimentResult` list.

## How to work with this codebase

### Running commands

```bash
python -m app.main ingest              # Ingest docs into Qdrant
python -m app.main query "question"    # Single query with tracing
python -m app.main chat                # Interactive chat
```

### Adding a new model

Add an entry to `litellm_config.yaml` under `model_list`, then use the `model_name` value with `--model`:

```bash
python -m app.main query "question" --model new-model-name
```

### Adding a new evaluator

Add a function to `app/eval/evaluators.py` that takes the output string and returns a score. Then wire it into `run_experiment()` in `app/eval/experiments.py` inside the `scores` dict.

### Tracing

Every function that calls an LLM should accept a `callbacks` parameter and pass it to LangChain's `.invoke(config={"callbacks": callbacks})`. The CLI creates the handler in `app/main.py` and threads it through.

### Docker networking

Services reference each other by container name (`postgres`, `redis`, `ollama`, `minio`, etc.). The app code runs on the host and uses `localhost` ports. If you move the app into Docker, change `app/config.py` defaults or `.env` values to use container names.

### Environment

- Python 3.11+
- Windows 11 (port 6379 is blocked by Hyper-V, so Redis maps to 6300)
- `.env` is gitignored; copy from `.env.example`
- The `data/docs/` directory is gitignored for any local markdown files used during ingestion

## Known issues

- **LiteLLM image (`ghcr.io/berriai/litellm:main-latest`)** requires a PostgreSQL database. The compose gives it a `DATABASE_URL` pointing to a `litellm` database on the shared Postgres instance. On first boot, Prisma migrations run automatically (~30s). The `master_key` in `litellm_config.yaml` must be a literal string (not an env var reference) so it registers correctly in the DB.
- Ollama model pulls must be done manually after first `docker compose up` (`docker compose exec ollama ollama pull llama3.2`).
- The `ingest` command uses `force_recreate=True` on the Qdrant collection, so re-running it wipes and rebuilds the entire index.
