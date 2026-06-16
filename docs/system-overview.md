# System overview

AgentGuard is a self-hosted AI reliability platform for teams building retrieval-augmented generation (RAG) and agentic applications.

It combines orchestration, model routing, protection, retrieval, observability, evaluation, and operator tooling into one deployable stack. The goal is to help teams ship AI systems that are easier to inspect, safer to operate, and faster to improve.

## What the platform does

At a high level, AgentGuard supports two primary runtime modes:

- **RAG flow** for grounded question answering over indexed knowledge
- **Agent flow** for multi-step reasoning with tools and MCP-connected systems

Both flows share the same platform foundation:

- **Open WebUI and CLI** for user interaction
- **Orchestrator API** for request routing and runtime dispatch
- **LiteLLM** for model access, routing, and policy enforcement
- **Guardrails** for prompt injection blocking, PII masking, and protection logic
- **Langfuse + OpenTelemetry** for traces, metrics, and execution visibility
- **Evaluation loops** for benchmarking, regression gating, and dataset-driven improvement

## Core architecture

AgentGuard is organized into five logical layers.

### 1. Interface layer

Users interact with the platform through:

- **Open WebUI** for browser-based chat and feedback collection
- **CLI** for ingestion, querying, agent runs, experiments, and operational workflows

This gives both end users and developers access to the same core platform capabilities.

### 2. Orchestration layer

The **Orchestrator API** is the shared runtime entry point.

It receives OpenAI-compatible requests and routes them into the correct execution path:

- the **RAG chain** when the task requires retrieval-based answering
- the **Agentic Workflow** when the task requires tools, multi-step reasoning, or MCP integration

This layer is where request handling becomes product behavior.

### 3. Knowledge and tool layer

The execution paths connect to external knowledge and actions through:

- **Qdrant** for vector retrieval
- **search, trace, scoring, and dataset tools** for agent workflows
- **MCP-connected services** for tool-based integrations such as GitHub access

This is the layer that turns a model response into a grounded or action-capable system response.

### 4. Model and protection layer

All model traffic is routed through **LiteLLM**, which acts as the platform gateway.

Behind that gateway, AgentGuard can use:

- **Ollama** for local models and embeddings
- **OpenRouter** for hosted generation and reasoning models

The gateway is paired with protection controls such as:

- prompt injection detection and blocking
- PII masking
- business-specific guardrails
- caching via Redis for reduced latency and token cost

This layer centralizes safety, consistency, and model-provider flexibility.

### 5. Observability and improvement layer

Every important runtime action is captured for monitoring and improvement.

AgentGuard uses:

- **Langfuse** for trace capture, scores, metadata, and datasets
- **OpenTelemetry** for instrumentation and telemetry fan-out
- **Jaeger** for distributed trace visualization
- **ClickHouse, Postgres, Redis, and MinIO** as supporting storage and analytics infrastructure

This observability foundation feeds a continuous improvement loop:

1. trace production behavior
2. monitor quality, latency, and errors
3. collect feedback and build datasets
4. run experiments and benchmarks
5. apply regression gates before changes are trusted

## Runtime paths

### RAG path

In the RAG path, a user query is embedded, matched against retrieved documents, and answered with grounded context.

Typical flow:

1. user sends a request through Open WebUI
2. the Orchestrator API routes the request to the RAG chain
3. LiteLLM requests embeddings from Ollama
4. Qdrant returns relevant document chunks
5. LiteLLM calls the selected generation model
6. the response and retrieval metadata are logged to Langfuse
7. the final answer is returned to the user

This path is optimized for grounded answers, explainability, and retrieval visibility.

### Agent path

In the agent path, the system reasons across one or more steps and invokes tools or MCP-connected services as needed.

Typical flow:

1. user sends a request through Open WebUI
2. the Orchestrator API routes the request to the agent workflow
3. the workflow invokes tools or MCP servers
4. LiteLLM calls the selected reasoning model
5. tool usage, intermediate execution, and outputs are logged to Langfuse
6. the final answer is returned to the user

This path is optimized for actionability, orchestration, and complex task completion.

## Why this architecture matters

From a product and platform perspective, this architecture creates four advantages.

### Unified operating model

RAG and agents do not live in separate products. They share a common runtime, protection model, and observability stack.

### Safer AI operations

Model access, guardrails, traces, and evaluation are built into the system rather than bolted on afterward.

### Deployment flexibility

Teams can combine local and hosted models, keep the stack self-hosted, and extend capabilities through MCP and internal tools.

### Faster improvement cycles

Because feedback, traces, datasets, and experiments are connected, the platform supports iterative quality improvement instead of one-off prompt tuning.

## Intended audience

AgentGuard is designed for:

- platform teams building internal AI systems
- engineering teams operating RAG or agentic products in production
- technical leaders who need stronger visibility, safety, and evaluation around LLM applications

## In one sentence

AgentGuard is a self-hosted operating layer for RAG and agentic applications that unifies orchestration, model access, protection, observability, and evaluation into one system.
