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
                     +-------------+-------------+
                     |                           |
            +--------v---------+       +---------v--------+
            |   RAG Chain       |       |   ReAct Agent    |
            |  (LangChain LCEL) |       |   (LangGraph)    |
            +----+--------+----+       +---+---------+----+
                 |        |                |         |
    +------------+    +---+          +-----+    +----+------+
    |                 |              |          |           |
  +-v-------+  +------v-----+  +----v---+  +--v-------+ +-v---------+
  |Retriever|  | LLM (Chat) |  |search_ |  |list_     | |score_     |
  |(Qdrant) |  | via LiteLLM|  |docs    |  |traces    | |response   |
  +---------+  +------------+  +--------+  +----------+ +-----------+

         All LLM calls route through LiteLLM proxy (port 4000)
         All calls are traced via Langfuse CallbackHandler

   +-------------------------------------------------------------------+
   |          Docker Compose Stack (14 services + 2 init)               |
   |                                                                    |
   |  langfuse-web (:3000)     langfuse-worker (:3030)                 |
   |  postgres (:5432)         clickhouse (:8123/:9000)                |
   |  redis (:6300->6379)      minio (:9090->9000, :9091->9001)       |
   |  ollama (:11434)          litellm (:4000)                         |
   |  qdrant (:6333/:6334)     portainer (:9443)   dozzle (:8080)     |
   |  rag-api (:8001)          openwebui (:3001)                       |
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
| **rag-api** | 8001 | FastAPI OpenAI-compatible wrapper around the RAG chain |
| **openwebui** | 3001 | Chat UI — connects to `rag-api`, every message triggers full RAG pipeline |
| **minio-init** | — | Creates `langfuse` bucket on first boot (runs once) |
| **litellm-init** | — | Seeds LiteLLM config (runs once) |

## Prerequisites

- **Docker** with Compose v2
- **NVIDIA GPU** + drivers (for Ollama GPU acceleration; CPU-only works but is slow)
- **Python 3.11+**
- ~15 GB RAM allocated to Docker (services have explicit CPU/memory limits)

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

### 3. Pull Ollama embedding model

```bash
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

### 6. Ask a question (simple RAG)

```bash
python -m app.main query "What is the AI Engineering Loop?"
```

### 7. Ask with the ReAct agent

The agent has tools for doc search, trace inspection, quality scoring, and dataset review:

```bash
python -m app.main agent "How is my RAG system performing?"
```

### 8. Interactive agent chat

```bash
python -m app.main agent-chat --session my-session
```

### 9. Chat via Open WebUI

Open [http://localhost:3001](http://localhost:3001), create an admin account on first visit, then select **agentguard-rag** from the model dropdown. Every message you send goes through the full RAG pipeline — embedding, Qdrant retrieval, LLM generation — and is traced in Langfuse.

### 10. View traces in Langfuse

Open [http://localhost:3000](http://localhost:3000) and log in with:
- **Email:** admin@local.dev
- **Password:** admin123456

Every query and chat message is automatically traced with full LLM call details, retrieval context, and latency.

## LLM Routing

All LLM requests go through the LiteLLM proxy, which provides a unified OpenAI-compatible API. Available models are configured in `litellm_config.yaml`:

| Model name | Backend | Notes |
|---|---|---|
| `nomic-embed-text` | Ollama (local) | Embedding only — the only model served locally |
| `openrouter-gemini-flash` | OpenRouter → Gemini 2.5 Flash Lite | Default chat model (needs API key) |
| `openrouter-mistral` | OpenRouter → Mistral Nemo | Alternative cloud model (needs API key) |

Switch models per query:

```bash
python -m app.main query "What is tracing?" --model openrouter-mistral
```

## ReAct Agent

Beyond simple RAG, AgentGuard includes a LangGraph ReAct agent that reasons about which tools to use:

| Tool | What it does |
|---|---|
| `search_docs` | Search the Qdrant knowledge base |
| `list_traces` | List recent Langfuse traces (ID, latency, input/output preview) |
| `get_trace_detail` | Drill into a specific trace with full observation tree |
| `score_response` | Run code-based evaluators on any text |
| `get_dataset_summary` | List datasets or inspect dataset items |

The agent can answer complex questions that require multiple tool calls — e.g., "How is my RAG system performing?" triggers trace inspection, detail drill-down, and quality scoring.

```bash
python -m app.main agent "What were my slowest queries?"
python -m app.main agent-chat --session demo
```

## Guardrails

Two custom guardrails run on every LiteLLM request by default, defined in `guardrails/custom_guardrails.py`:

| Guardrail | Mode | What it does |
|---|---|---|
| **Prompt injection** | pre_call | Blocks 12 regex patterns (jailbreak, ignore instructions, DAN, role hijacking, system prompt exfiltration, etc.) before the request reaches the LLM. Returns HTTP 400. |
| **PII masking** | post_call | Redacts email addresses, SSNs, credit card numbers, and phone numbers from LLM responses |

Both are registered in `litellm_config.yaml` with `default_on: true` — no per-request opt-in needed.

## Open WebUI

AgentGuard ships with [Open WebUI](https://github.com/open-webui/open-webui) as a chat interface at **http://localhost:3001**. It connects to `rag-api` (`app/api.py`) — a thin FastAPI wrapper that exposes the RAG chain as an OpenAI-compatible API.

| Virtual model | Backing LiteLLM model | Notes |
|---|---|---|
| `agentguard-rag` | `openrouter-gemini-flash` | Default |
| `agentguard-rag-mistral` | `openrouter-mistral` | Alternative |

Every message sent via Open WebUI triggers the full RAG pipeline: query embedding → Qdrant similarity search → LLM generation. The trace appears in Langfuse within seconds. To confirm embeddings are firing:

```bash
docker compose logs litellm --tail 20 | grep embeddings
```

## Evaluation

### Code-based evaluators (`app/eval/evaluators.py`)

- `has_source_citation` - checks if the response references a source
- `is_within_length` - enforces word count limit
- `contains_no_hallucination_markers` - flags hedging language
- `is_valid_json` - validates JSON output format

### LLM-as-judge (`app/eval/evaluators.py`)

Binary scoring on three criteria: **relevance**, **faithfulness**, and **completeness**.

### DeepEval metrics (`app/eval/deepeval_metrics.py`)

LLM-judged evaluation using [DeepEval](https://github.com/confident-ai/deepeval), routing judge calls through LiteLLM:

| Metric | What it measures |
|---|---|
| `FaithfulnessMetric` | Is the answer grounded in retrieved context? |
| `AnswerRelevancyMetric` | Does the answer address the question? |
| `ContextualRelevancyMetric` | Are the retrieved chunks relevant? |
| `HallucinationMetric` | Does the answer contain fabricated info? |

Run against a Langfuse dataset — scores are pushed back to Langfuse automatically:

```bash
python -m app.main evaluate --dataset rag-eval-v1
python -m app.main evaluate --dataset rag-eval-v1 --metrics faithfulness,hallucination
```

### Experiment runner (`app/eval/experiments.py`)

Compare multiple models against a Langfuse dataset with code-based evaluators:

```python
from app.eval.experiments import run_experiment, print_results

results = run_experiment(
    dataset_name="rag-eval-v1",
    models=["openrouter-gemini-flash", "openrouter-mistral"],
    experiment_name="model-comparison-001",
)
print_results(results)
```

## Testing

```bash
pytest -m "not integration"   # 135 unit tests, no Docker needed (~9s)
pytest -m integration          # 18 integration tests, Docker stack required
pytest -v                      # Full suite
```

Unit tests cover agent tools, graph structure, DeepEval metric wiring, guardrails, evaluators, config, RAG chain, and ingestion. Integration tests verify service health, guardrail HTTP behavior, RAG API health, agent end-to-end, and RAG pipeline. Integration tests auto-skip when the Docker stack isn't running.

## Project Structure

```
.
├── docker-compose.yml        # 14-service stack + 2 init containers
├── litellm_config.yaml       # LiteLLM model routing + guardrails config
├── requirements.txt          # Python dependencies
├── pyproject.toml            # pytest configuration
├── .env.example              # Environment template
├── app/
│   ├── config.py             # Pydantic settings from .env
│   ├── tracing.py            # Langfuse CallbackHandler factory
│   ├── main.py               # CLI entry point (ingest/query/chat/agent/evaluate)
│   ├── rag/
│   │   ├── ingest.py         # Document loading, chunking, embedding
│   │   └── chain.py          # LCEL retrieval-augmented generation chain
│   ├── agent/
│   │   ├── tools.py          # 5 agent tools (search, traces, scoring, datasets)
│   │   ├── graph.py          # LangGraph ReAct agent (StateGraph + ToolNode)
│   │   └── prompts.py        # Agent system prompt
│   └── eval/
│       ├── evaluators.py     # Code-based + LLM-as-judge evaluators
│       ├── experiments.py    # Multi-model experiment runner
│       ├── deepeval_metrics.py  # LiteLLM model wrapper + DeepEval metric factories
│       └── deepeval_runner.py   # Evaluation runner with Langfuse score push
├── guardrails/
│   └── custom_guardrails.py  # Prompt injection + PII masking guards
├── app/
│   └── api.py                # FastAPI OpenAI-compatible RAG API (for Open WebUI)
└── tests/
    ├── test_agent_tools.py   # 22 tests: all 5 tool functions
    ├── test_agent_graph.py   # 13 tests: graph structure, routing, prompts
    ├── test_deepeval_metrics.py # 14 tests: LiteLLM model, metric factories
    ├── test_agent_integration.py # 5 tests: agent e2e (requires Docker)
    ├── test_guardrails.py    # 43 tests: injection detection, PII masking
    ├── test_evaluators.py    # 16 tests: all code-based evaluators
    ├── test_config.py        # 3 tests: settings defaults + overrides
    ├── test_chain.py         # 9 tests: format_docs, prompt, e2e query
    ├── test_ingest.py        # 10 tests: chunking, loading, scraping
    └── test_integration.py   # 8 tests: service health, RAG API, guardrails, RAG
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
