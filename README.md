# AgentGuard

**The QA layer for agentic AI that everybody loves to ignore.**

A self-hosted RAG application with full observability, guardrails, and evaluation built in — implementing the complete [AI Engineering Loop](https://langfuse.com/academy/ai-engineering-loop): Trace, Monitor, Build Datasets, Experiment, and Evaluate.

The application answers questions about Langfuse's own documentation (a meta twist) and uses Langfuse to observe itself doing it.

## Architecture

```
                          +------------------+
                          |   CLI / Chat     |
                          |  (app/main.py)   |
                          +--------+---------+
                                   |
                          +--------v---------+
                          |   RAG Chain       |
                          |  (LangChain LCEL) |
                          +----+--------+----+
                               |        |
                  +------------+        +------------+
                  |                                  |
         +--------v--------+              +----------v---------+
         |    Retriever     |              |     LLM (Chat)     |
         |   (Qdrant)       |              |   via LiteLLM      |
         +---------+--------+              +----------+---------+
                   |                                  |
         +---------v--------+              +----------v---------+
         |  Embeddings       |              | Ollama (local)     |
         |  nomic-embed-text |              | OpenRouter (cloud) |
         +------------------+              +--------------------+
                                                     
         All LLM calls route through LiteLLM proxy (port 4000)
         All calls are traced via Langfuse CallbackHandler

   +-------------------------------------------------------------------+
   |                    Docker Compose Stack                            |
   |                                                                    |
   |  langfuse-web (:3000)     langfuse-worker (:3030)                 |
   |  postgres (:5432)         clickhouse (:8123/:9000)                |
   |  redis (:6300->6379)      minio (:9090->9000, :9091->9001)       |
   |  ollama (:11434)          litellm (:4000)                         |
   |  qdrant (:6333/:6334)                                             |
   +-------------------------------------------------------------------+
```

## Services

| Service | Port(s) | Purpose |
|---|---|---|
| **langfuse-web** | 3000 | Langfuse UI and API |
| **langfuse-worker** | 3030 (local only) | Background trace/event processing |
| **postgres** | 5432 (local only) | Langfuse relational database |
| **clickhouse** | 8123, 9000 (local only) | Langfuse analytics storage |
| **redis** | 6300 (host) -> 6379 (container) | Langfuse cache/queue |
| **minio** | 9090 (API), 9091 (console, local only) | S3-compatible blob storage |
| **ollama** | 11434 | Local LLM serving (GPU) |
| **litellm** | 4000 | OpenAI-compatible LLM proxy |
| **qdrant** | 6333 (HTTP), 6334 (gRPC, local only) | Vector database |
| **portainer** | 9443 (HTTPS) | Container management UI |
| **dozzle** | 8080 | Real-time log viewer |

## Prerequisites

- **Docker** with Compose v2
- **NVIDIA GPU** + drivers (for Ollama GPU acceleration; CPU-only works but is slow)
- **Python 3.11+**
- ~8 GB RAM for the full stack

## Quick Start

### 1. Clone and configure

```bash
cp .env.example .env
# Edit .env if you want to change passwords or add an OpenRouter API key
```

### 2. Start the Docker stack

```bash
docker compose up -d
```

Wait for all services to be healthy:

```bash
docker compose ps
```

### 3. Pull Ollama models

```bash
docker compose exec ollama ollama pull llama3.2
docker compose exec ollama ollama pull nomic-embed-text
```

### 4. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 5. Ingest documents

Scrapes the Langfuse Academy pages and stores embeddings in Qdrant:

```bash
python -m app.main ingest
```

### 6. Ask a question

```bash
python -m app.main query "What is the AI Engineering Loop?"
```

### 7. Interactive chat

```bash
python -m app.main chat --session my-session --user demo-user
```

### 8. View traces in Langfuse

Open [http://localhost:3000](http://localhost:3000) and log in with:
- **Email:** admin@local.dev
- **Password:** admin

Every query and chat message is automatically traced with full LLM call details, retrieval context, and latency.

## LLM Routing

All LLM requests go through the LiteLLM proxy, which provides a unified OpenAI-compatible API. Available models are configured in `litellm_config.yaml`:

| Model name | Backend | Notes |
|---|---|---|
| `llama3` | Ollama (llama3.2) | Default chat model |
| `mistral` | Ollama (mistral) | Alternative local model |
| `nomic-embed-text` | Ollama | Embedding model |
| `openrouter-llama3` | OpenRouter | Cloud fallback (needs API key) |
| `openrouter-mistral` | OpenRouter | Cloud fallback (needs API key) |

Switch models per query:

```bash
python -m app.main query "What is tracing?" --model mistral
```

## Evaluation

### Code-based evaluators (`app/eval/evaluators.py`)

- `has_source_citation` - checks if the response references a source
- `is_within_length` - enforces word count limit
- `contains_no_hallucination_markers` - flags hedging language
- `is_valid_json` - validates JSON output format

### LLM-as-judge (`app/eval/evaluators.py`)

Binary scoring on three criteria: **relevance**, **faithfulness**, and **completeness**.

### Experiment runner (`app/eval/experiments.py`)

Compare multiple models against a Langfuse dataset:

```python
from app.eval.experiments import run_experiment, print_results

results = run_experiment(
    dataset_name="rag-eval-v1",
    models=["llama3", "mistral"],
    experiment_name="model-comparison-001",
)
print_results(results)
```

## Project Structure

```
.
├── docker-compose.yml        # 11-service stack definition
├── litellm_config.yaml       # LiteLLM model routing + guardrails config
├── requirements.txt          # Python dependencies
├── pyproject.toml            # pytest configuration
├── .env.example              # Environment template
├── app/
│   ├── config.py             # Pydantic settings from .env
│   ├── tracing.py            # Langfuse CallbackHandler factory
│   ├── main.py               # CLI entry point (ingest/query/chat)
│   ├── rag/
│   │   ├── ingest.py         # Document loading, chunking, embedding
│   │   └── chain.py          # LCEL retrieval-augmented generation chain
│   └── eval/
│       ├── evaluators.py     # Code-based + LLM-as-judge evaluators
│       └── experiments.py    # Multi-model experiment runner
├── guardrails/
│   └── custom_guardrails.py  # Prompt injection + PII masking guards
└── tests/
    ├── test_guardrails.py    # 32 tests: injection detection, PII masking
    ├── test_evaluators.py    # 16 tests: all code-based evaluators
    ├── test_config.py        # 3 tests: settings defaults + overrides
    ├── test_chain.py         # 9 tests: format_docs, prompt, e2e query
    ├── test_ingest.py        # 10 tests: chunking, loading, scraping
    └── test_integration.py   # 7 tests: service health, guardrails, RAG
```

## The AI Engineering Loop

This project implements all five phases from the Langfuse Academy curriculum:

1. **Trace** - Every LangChain call is automatically captured via the Langfuse `CallbackHandler`, recording inputs, outputs, latencies, token usage, and retrieval context.

2. **Monitor** - The Langfuse dashboard provides real-time visibility into trace volumes, latency distributions, error rates, and cost tracking.

3. **Build Datasets** - Traces can be promoted to evaluation datasets directly in the Langfuse UI, creating labeled examples from real usage.

4. **Experiment** - The experiment runner (`app/eval/experiments.py`) systematically compares model variants against datasets, recording all results back to Langfuse.

5. **Evaluate** - Code-based evaluators provide deterministic checks; the LLM-as-judge evaluator provides nuanced quality assessment. Both feed scores into Langfuse for tracking over time.

## Windows Notes

Redis is mapped to host port **6300** instead of the default 6379 due to Windows dynamic port exclusion ranges (Hyper-V/WSL reserves port ranges that can include 6379). All container-internal ports remain at their defaults.
