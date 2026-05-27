# AgentGuard

**AgentGuard is a self-hosted control layer for preventing costly incidents in AI applications.**

It supports both **RAG** and **agentic** applications by helping teams detect, evaluate, and block failures before they reach users.

When an AI assistant hallucinates a discount, misstates company policy, leaks sensitive data, or regresses after a prompt, model, retrieval, or tool change, the result is not just a bad answer — it is a business incident.

## Why this matters

AI applications fail in expensive ways.

A RAG assistant can hallucinate a discount or refund policy. An agent can take the wrong action. A model update can silently degrade answer quality. A prompt change can introduce unsafe behavior or expose sensitive data.

These failures are not just model mistakes — they become business incidents.

AgentGuard is designed to help teams detect, evaluate, and reduce those incidents before they become customer-visible.

## Problem

LLM applications — whether RAG assistants or agentic systems — can create customer-facing incidents by hallucinating offers, exposing PII, giving unsafe answers, taking incorrect actions, or silently regressing after system changes.

## Who this is for

AgentGuard is for teams building or operating AI systems where reliability matters, including:

- AI engineers building RAG or agentic applications
- platform teams standardizing how AI applications are observed and evaluated
- technical product owners responsible for quality, safety, and release confidence
- teams working with sensitive knowledge, regulated workflows, or business-critical user interactions

It is especially useful when failures can create financial, compliance, operational, or reputational risk.

## Success Metric

The percentage of AI incidents detected or prevented before they become customer-visible.

## How AgentGuard helps

AgentGuard combines four control mechanisms for AI applications:

- **Observability** — trace requests, retrieval steps, tool usage, model behavior, latency, and failure modes
- **Business protection** — reduce unsafe behavior, policy bypass, and sensitive data exposure
- **PII protection** — detect and redact sensitive data in model outputs
- **Golden dataset evaluation** — test critical business scenarios against a curated set of known-good examples before and after changes

## What is a golden dataset?

A golden dataset is a curated collection of representative prompts and expected answers that defines what correct behavior looks like for your AI application.

It works like a regression suite for an LLM system. For example, you can include high-risk scenarios such as:
- pricing and discount questions
- refund and policy questions
- compliance-sensitive prompts
- sensitive data handling
- known production failure cases

When you change a prompt, model, retriever, or tool, AgentGuard can run those golden examples again to detect regressions before the change becomes customer-visible.

## Architecture

```mermaid
flowchart TD
    U[User]
    CLI[CLI / Chat]
    WEB[Open WebUI]
    API[rag-api]

    U --> CLI
    U --> WEB
    WEB --> API
    CLI --> RAG
    CLI --> AGENT
    API --> RAG

    subgraph App["Application Layer"]
        RAG[RAG Chain]
        AGENT[Agentic Workflow]
    end

    subgraph Knowledge["Knowledge + Tools"]
        Q[Qdrant Retriever]
        TOOLS[Search / Trace / Scoring / Dataset Tools]
    end

    subgraph Model["Model Routing + Protection"]
        LLM[LiteLLM Gateway]
        PROTECT[Business Protection<br/>Prompt Injection Blocking<br/>PII Masking]
        CACHE[Redis Cache<br/>Query Caching / Token Savings]
    end

    subgraph Telemetry["Observability + Telemetry"]
        LF[Langfuse]
        OTEL[OpenTelemetry SDK]
        COLLECTOR[otel-collector]
        JAEGER[Jaeger]
        EVAL[Golden Dataset Evaluation<br/>Release Confidence]
    end

    subgraph Infra["Infrastructure"]
        OLLAMA[Ollama<br/>Local LLM + Embeddings]
        PG[Postgres]
        CH[ClickHouse]
        REDIS[Redis]
        MINIO[MinIO]
    end

    RAG --> Q
    RAG --> LLM
    AGENT --> TOOLS
    AGENT --> LLM

    LLM --> PROTECT
    LLM --> OLLAMA
    LLM --> CACHE
    CACHE -.-> REDIS

    RAG --> LF
    AGENT --> LF
    LLM --> LF
    EVAL --> LF

    API --> OTEL
    OTEL --> COLLECTOR
    COLLECTOR --> JAEGER
    COLLECTOR --> LF

    LF --> PG
    LF --> CH
    LF --> REDIS
    LF --> MINIO
```

## Message Flow

The diagram below shows how a user message moves through the runtime path across the main application services.

```mermaid
sequenceDiagram
    participant User
    participant OpenWebUI
    participant RAGAPI as rag-api
    participant LiteLLM
    participant Ollama
    participant Qdrant
    participant Langfuse

    User->>OpenWebUI: Send message
    OpenWebUI->>RAGAPI: OpenAI-compatible chat request

    RAGAPI->>LiteLLM: Create embedding request
    LiteLLM->>Ollama: Generate embedding
    Ollama-->>LiteLLM: Embedding vector
    LiteLLM-->>RAGAPI: Embedding response

    RAGAPI->>Qdrant: Similarity search with embedding
    Qdrant-->>RAGAPI: Relevant document chunks

    RAGAPI->>LiteLLM: Generate answer with retrieved context
    LiteLLM-->>RAGAPI: Final response

    RAGAPI->>Langfuse: Send trace, metadata, scores, retrieval context
    LiteLLM->>Langfuse: Log model calls and LLM metadata

    RAGAPI-->>OpenWebUI: Final answer
    OpenWebUI-->>User: Render response
```

## Platform Components

AgentGuard runs as a self-hosted stack that combines observability, retrieval, model routing, UI, evaluation, and telemetry into one environment for operating AI applications safely.

| Component | Port(s) | Role in the platform |
|---|---|---|
| **langfuse-web** | 3000 | Observability UI and API for traces, scores, and datasets |
| **langfuse-worker** | 3030 (local only) | Background processing for trace and event ingestion |
| **postgres** | 5432 (local only) | Relational storage for Langfuse and supporting services |
| **clickhouse** | 8123, 9000 (local only) | Analytics store for high-volume observability data |
| **redis** | 6300 (host) -> 6379 (container) | Cache and queue backend |
| **minio** | 9090 (API), 9091 (console, local only) | S3-compatible object storage |
| **ollama** | 11434 | Local model runtime to support local LLMs and embeddings |
| **litellm** | 4000 | OpenAI-compatible model gateway and protection enforcement layer |
| **qdrant** | 6333 (HTTP), 6334 (gRPC, local only) | Vector store for retrieval |
| **rag-api** | 8001 | OpenAI-compatible API surface for the RAG application |
| **openwebui** | 3001 | End-user chat interface for interacting with the application |
| **otel-collector** | 4317, 4318, 13133 | OpenTelemetry collection and fan-out to observability backends |
| **jaeger** | 16686 | Trace visualization UI for end-to-end OpenTelemetry traces |
| **portainer** | 9443 | Container administration UI |
| **dozzle** | 8080 | Real-time container log viewer |
| **minio-init** | — | One-time initialization of object storage buckets |
| **litellm-init** | — | One-time initialization of LiteLLM configuration |

## Why self-hosted?

AgentGuard is currently designed as a self-hosted platform so teams can evaluate, observe, and protect AI applications in an environment they control.

This matters especially when working with:
- internal knowledge bases
- sensitive prompts and responses
- regulated or compliance-sensitive workflows
- early-stage systems that need infrastructure-level visibility for debugging and iteration

A self-hosted setup also makes it easier to inspect the full runtime path — from retrieval and model routing to tracing, scoring, and protection — without depending on a managed platform.

Cloud deployment is planned next. In particular, porting the stack to **Google Cloud** is expected to be a near-term step so teams can keep the same control model while reducing operational overhead.

## Roadmap

AgentGuard is currently focused on a self-hosted deployment model so teams can run observability, protection, and evaluation in an environment they control.

Near-term roadmap priorities include:

- **Google Cloud deployment** to make the platform easier to operate in production environments
- **stronger release workflows** for evaluating prompt, model, and retrieval changes before rollout
- **richer protection controls** for business-policy enforcement and sensitive-data handling
- **improved operational visibility** across traces, scoring, caching, and agent behavior

The goal is to evolve AgentGuard from a strong self-hosted reference platform into a production-ready control layer for AI applications.

## Prerequisites

To run AgentGuard locally, you need:

- **Docker** with Compose v2
- **Python 3.11+**
- **~15 GB RAM** allocated to Docker
- **NVIDIA GPU + drivers** if you want Ollama GPU acceleration  
  (CPU-only works, but will be slower)

## Quick Start

The fastest way to experience AgentGuard is:

### 1. Clone and configure

```bash
cp .env.example .env
# Edit .env if you want to change passwords or add an OpenRouter API key
```

### 2. Start the platform

```bash
docker compose up -d
```

Check that services are healthy:

```bash
docker compose ps
```

### 3. Pull the embedding model

```bash
docker compose exec ollama ollama pull nomic-embed-text
```

### 4. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 5. Ingest the knowledge base

This step loads the NorthstarCRM knowledge base from `mock_corpus/` and indexes it in Qdrant for retrieval.

```bash
python -m app.main ingest
```

### 6. Test the RAG path

```bash
python -m app.main query "Does the Starter plan include SAML SSO?"
```

### 7. Test the agentic path

The agent can combine document search, trace inspection, response scoring, and dataset inspection.

```bash
python -m app.main agent "How is my RAG system performing?"
```

### 8. Start an interactive agent session

```bash
python -m app.main agent-chat --session my-session
```

### 9. Use the web chat UI

Open [http://localhost:3001](http://localhost:3001), create an admin account on first visit, then select **agentguard-rag** from the model dropdown.

Every message you send goes through the full application stack, including retrieval, model routing, tracing, and protection layers.

### 10. Inspect traces and scores

Open [http://localhost:3000](http://localhost:3000) and sign in with:

- **Email:** admin@local.dev
- **Password:** admin123456

You should now see traces with request inputs, outputs, retrieval context, latency, and evaluation data.

## Model Routing

All model requests go through the LiteLLM proxy, which provides a unified OpenAI-compatible API. Available models are configured in `litellm_config.yaml`:

| Model name | Backend | Notes |
|---|---|---|
| `nomic-embed-text` | Ollama (local) | Embedding only — the only model served locally |
| `openrouter-gemini-flash` | OpenRouter → Gemini 2.5 Flash Lite | Default chat model (needs API key) |
| `openrouter-mistral` | OpenRouter → Mistral Nemo | Alternative cloud model (needs API key) |

Switch models per query:

```bash
python -m app.main query "What is tracing?" --model openrouter-mistral
```

## Agentic Workflow

Beyond simple RAG, AgentGuard includes a LangGraph-powered agentic workflow that reasons about which tools to use:

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

## Business Protection

AgentGuard helps reduce the risk of customer-facing AI incidents by screening requests and responses for unsafe or non-compliant behavior.

This includes preventing common failure modes such as:
- attempts to override system instructions
- unsafe or misleading responses
- accidental exposure of personally identifiable information (PII)
- behavior that drifts away from expected policy or business rules

In the current implementation, AgentGuard applies two built-in protections on LiteLLM traffic by default:

| Protection | What it does | Business value |
|---|---|---|
| **Prompt injection blocking** | Detects and blocks common attempts to manipulate or override the assistant’s instructions before the model responds | Reduces the risk of policy bypass, unsafe behavior, and untrusted outputs |
| **PII masking** | Redacts email addresses, SSNs, credit card numbers, and phone numbers from model responses | Reduces the risk of exposing sensitive user or customer data |

Both protections are enabled by default in `litellm_config.yaml`, so they apply automatically without per-request configuration.

## Release Confidence

AgentGuard helps teams verify that an AI application still behaves correctly after changes to prompts, models, retrieval logic, or tools.

Instead of waiting for users to discover regressions in production, teams can evaluate known high-risk scenarios in advance and track quality over time.

This supports release confidence in three ways:

| Capability | What it checks | Why it matters |
|---|---|---|
| **Automated response checks** | Verifies basics such as citation presence, response length, hallucination markers, and output format | Catches simple quality failures before they become user-visible |
| **LLM-based quality review** | Scores answers for relevance, faithfulness, and completeness | Helps assess whether responses are actually useful and grounded |
| **Golden dataset regression testing** | Replays known-good business scenarios across prompts, models, and retrieval changes | Helps prevent silent regressions after system updates |

### Automated response checks (`app/eval/evaluators.py`)

AgentGuard includes deterministic checks for common response-quality issues:

- `has_source_citation` — checks whether the response references a source
- `is_within_length` — enforces a response length limit
- `contains_no_hallucination_markers` — flags hedging language that may indicate weak confidence or unsupported claims
- `is_valid_json` — validates JSON output format when structured output is expected

### LLM-based quality review (`app/eval/evaluators.py`)

AgentGuard also supports model-based review of answer quality using three dimensions:

- **relevance** — does the answer address the question?
- **faithfulness** — is the answer grounded in the retrieved context?
- **completeness** — does the answer cover what the user asked?

### Advanced quality metrics (`app/eval/deepeval_metrics.py`)

For deeper analysis, AgentGuard integrates [DeepEval](https://github.com/confident-ai/deepeval) through LiteLLM:

| Metric | What it measures |
|---|---|
| `FaithfulnessMetric` | Is the answer grounded in retrieved context? |
| `AnswerRelevancyMetric` | Does the answer address the question? |
| `ContextualRelevancyMetric` | Are the retrieved chunks relevant? |
| `HallucinationMetric` | Does the answer contain fabricated information? |

Run these checks against a golden dataset and push the results back to Langfuse automatically:

```bash
python -m app.main evaluate --dataset rag-eval-v1
python -m app.main evaluate --dataset rag-eval-v1 --metrics faithfulness,hallucination
```

### Comparing models and configurations (`app/eval/experiments.py`)

AgentGuard can compare multiple models against the same golden dataset so teams can make safer rollout decisions:

```bash
python -m app.main experiment \
  --dataset rag-golden-set \
  --models openrouter-gemini-flash,openrouter-mistral \
  --limit 10
```

### Benchmark suite (`app/eval/benchmark.py`)

AgentGuard includes a structured benchmark for evaluating RAG pipeline quality across five metrics simultaneously, with support for ablation comparisons (guardrails on vs. off vs. no retrieval).

| Metric | What it measures | How it works |
|---|---|---|
| **Retrieval hit rate** | Did the pipeline retrieve a relevant document? | Filename or full-path match against gold docs |
| **Factual coverage** | How much of the expected answer did the response cover? | Stop-word-filtered token overlap over expected facts |
| **Correct escalation rate** | Did the assistant escalate when it should (and not when it shouldn't)? | 15 escalation-intent phrase patterns |
| **Policy violation rate** | Did the response violate any NorthstarCRM sales policies? | LLM-as-judge with 7 business rules |
| **Answer helpfulness (1–5)** | How well does the response progress the sales conversation? | LLM-as-judge scored 1–5 |

Run the benchmark in different modes to measure the impact of guardrails and retrieval:

```bash
python -m app.main benchmark                              # Full pipeline (RAG + guardrails)
python -m app.main benchmark --compare                    # All 3 modes side-by-side
python -m app.main benchmark --limit 5 --no-llm-judge    # Fast smoke-test (code metrics only)
python -m app.main benchmark --mode no-guardrails         # Ablation: guardrails disabled
python -m app.main benchmark --mode direct                # Baseline: bare LLM, no retrieval
```

The benchmark covers questions from `mock_corpus/07_benchmark/`, including standard questions and harder edge cases (competitor-match requests, partial feature overlap, custom legal paper, ambiguous procurement questions).

## Testing and Coverage

AgentGuard includes broad automated test coverage across core system components, with fast unit tests for day-to-day development and integration tests for validating the full stack.

```bash
pytest -m "not integration"   # 263 unit tests, no Docker needed (~5s)
pytest -m integration          # 17 integration tests, Docker stack required
pytest -v                      # Full suite
```

Coverage includes agent tools, graph structure, DeepEval metric wiring, business protections, evaluators, configuration, RAG chain behavior, corpus ingestion, CLI dispatch, service error mapping, API routes, benchmark metrics, and end-to-end integration flows.

## Project Structure

```
.
├── docker-compose.yml        # 14 services + 2 init containers
├── litellm_config.yaml       # LiteLLM model routing + guardrails config
├── requirements.txt          # Python dependencies
├── pyproject.toml            # pytest configuration
├── .env.example              # Environment template
├── app/
│   ├── main.py               # Bare entry point → app/cli/app.py::main()
│   ├── core/
│   │   ├── config.py         # Pydantic settings from .env (+ shim at app/config.py)
│   │   ├── tracing.py        # Langfuse client singleton + CallbackHandler factory
│   │   ├── telemetry.py      # OTel SDK bootstrap (+ shim at app/telemetry.py)
│   │   ├── logging.py        # configure_logging() — called once by CLI main()
│   │   └── ids.py            # request_id() / completion_id() generators
│   ├── cli/
│   │   ├── app.py            # Argument parser + dispatch via args.func(args)
│   │   ├── common.py         # Shared CLI helpers (flush, etc.)
│   │   └── commands/         # One module per command domain
│   │       ├── ingest.py     # ingest
│   │       ├── query.py      # query, chat
│   │       ├── agent.py      # agent, agent-chat
│   │       ├── evaluate.py   # evaluate, online-eval
│   │       ├── experiment.py # experiment
│   │       ├── dataset.py    # seed-dataset
│   │       ├── regression.py # regression-gate
│   │       └── benchmark.py  # benchmark
│   ├── api/
│   │   ├── app.py            # create_app() FastAPI factory
│   │   ├── schemas.py        # Message, ChatRequest Pydantic models
│   │   ├── streaming.py      # SSE stream_from_result()
│   │   ├── routes/           # Thin handlers: validate → call service → return
│   │   │   ├── health.py
│   │   │   ├── models.py
│   │   │   ├── webhook.py
│   │   │   └── chat.py
│   │   └── services/         # Business logic, one file per concern
│   │       ├── models_service.py   # MODELS, DIRECT_MODELS, get_model_list()
│   │       ├── health_service.py   # _probe(), check_all()
│   │       ├── feedback_service.py # parse_feedback(), push_score(), handle_webhook()
│   │       ├── direct_llm.py       # Direct LiteLLM call with error mapping
│   │       ├── rag_llm.py          # RAG chain invocation via rag_service
│   │       └── chat_service.py     # Dispatch orchestrator + response builder
│   ├── rag/
│   │   ├── service.py        # Stable interface: ingest(), query(), build_chain()
│   │   ├── ingest.py         # Document loading, chunking, embedding
│   │   └── chain.py          # LCEL RAG chain + ScoredRetriever
│   ├── agent/
│   │   ├── service.py        # Stable interface: run(), build_chat_session(), respond()
│   │   ├── tools.py          # 5 agent tools (search, traces, scoring, datasets)
│   │   ├── graph.py          # LangGraph ReAct agent (StateGraph + ToolNode)
│   │   └── prompts.py        # Agent system prompt
│   └── eval/
│       ├── service.py        # Stable interface: evaluate(), experiment(), regression_gate()
│       ├── evaluators.py     # Code-based + LLM-as-judge evaluators
│       ├── experiments.py    # Multi-model experiment runner
│       ├── deepeval_metrics.py  # LiteLLM model wrapper + DeepEval metric factories
│       ├── deepeval_runner.py   # Evaluation runner with Langfuse score push
│       └── benchmark.py      # Benchmark runner: 3 modes × 5 metrics over NorthstarCRM corpus
├── guardrails/
│   └── custom_guardrails.py  # Prompt injection + PII masking guards
└── tests/
    ├── test_agent_tools.py      # 22 tests: all 5 tool functions
    ├── test_agent_graph.py      # 13 tests: graph structure, routing, prompts
    ├── test_deepeval_metrics.py # 14 tests: LiteLLM model, metric factories
    ├── test_guardrails.py       # 43 tests: injection detection, PII masking
    ├── test_evaluators.py       # 16 tests: all code-based evaluators
    ├── test_config.py           # 3 tests: settings defaults + overrides
    ├── test_chain.py            # 9 tests: format_docs, prompt, e2e query
    ├── test_ingest.py           # 21 tests: corpus loader (md, jsonl, recursive, source path)
    ├── test_cli.py              # 29 tests: parser recognition, dispatch, session/user flags
    ├── test_services.py         # 35 tests: service error mapping + flow logic
    ├── test_api_routes.py       # 16 tests: route handlers (skipped without fastapi)
    ├── test_benchmark.py        # 38 tests: loaders, retrieval hit, factual coverage, escalation, _agg, CLI
    ├── test_agent_integration.py # 5 tests: agent e2e (requires Docker)
    └── test_integration.py      # 8 tests: service health, RAG API, guardrails
```

## The Continuous Improvement Loop

AgentGuard implements a closed-loop improvement cycle that connects production traffic back to evaluation, enabling teams to iterate on AI systems with confidence.

1. **Trace** — Every LangChain call is automatically captured via the Langfuse `CallbackHandler`, recording inputs, outputs, latencies, token usage, and retrieval context.

2. **Monitor** — The Langfuse dashboard provides real-time visibility into trace volumes, latency distributions, error rates, and cost tracking. Online evaluators run automatically on new traces.

3. **Build Datasets** — User feedback (thumbs-up/down via Open WebUI) is automatically synced and promoted into the `rag-golden-set` Langfuse dataset. Curated benchmark items live in `mock_corpus/07_benchmark/`.

4. **Experiment** — The experiment runner (`app/eval/experiments.py`) systematically compares model variants against golden datasets, recording all results back to Langfuse.

5. **Evaluate** — Code-based evaluators, DeepEval metrics, and the benchmark runner provide layered quality signals. The regression gate (`app/eval/service.py::regression_gate()`) enforces pass/fail thresholds before changes go live.

## Windows Notes

Redis is mapped to host port **6300** instead of the default 6379 due to Windows dynamic port exclusion ranges (Hyper-V/WSL reserves port ranges that can include 6379). All container-internal ports remain default.