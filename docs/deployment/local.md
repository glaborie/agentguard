# Local deployment

This guide covers how to run AgentGuard locally for development and evaluation.

## Prerequisites

To run AgentGuard locally, you need:

- **Docker** with Compose v2
- **Python 3.11+**
- **~15 GB RAM** allocated to Docker
- **NVIDIA GPU + drivers** if you want Ollama GPU acceleration  
  (CPU-only works, but will be slower)

## Why self-hosted?

AgentGuard is currently designed as a self-hosted platform so teams can evaluate, observe, and protect AI applications in an environment they control.

This matters especially when working with:
- internal knowledge bases
- sensitive prompts and responses
- regulated or compliance-sensitive workflows
- early-stage systems that need infrastructure-level visibility for debugging and iteration

A self-hosted setup also makes it easier to inspect the full runtime path — from retrieval and model routing to tracing, scoring, and protection — without depending on a managed platform.

## Quick start

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

## Model routing

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

## Windows notes

Redis is mapped to host port **6300** instead of the default 6379 due to Windows dynamic port exclusion ranges (Hyper-V/WSL reserves port ranges that can include 6379). All container-internal ports remain standard.
