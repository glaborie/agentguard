# AgentGuard — Deployment Guide

This document covers the full startup sequence for a fresh deployment and the steps required when switching or updating the knowledge base corpus.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Docker + Compose v2 | `docker compose version` |
| NVIDIA GPU + drivers | optional but recommended for Ollama |
| Python | 3.11+ |
| ~15 GB RAM | allocated to Docker |

---

## 1. First-Time Setup

### 1.1 Configure environment

```bash
cp .env.example .env
# Required: set OPENROUTER_API_KEY for cloud LLM access
# Optional: change passwords, CORS origins, collection name
```

Key variables in `.env`:

| Variable | Default | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | *(empty)* | Required for cloud LLM via OpenRouter |
| `QDRANT_COLLECTION` | `northstar_crm` | Change if using a different corpus |
| `CORS_ORIGINS` | `*` | Comma-separated origins, e.g. `http://localhost:3100` |
| `LITELLM_MASTER_KEY` | `sk-litellm-dev-key` | Auth key for the LiteLLM proxy |
| `DEFAULT_MODEL` | `openrouter-gemini-flash` | Default chat LLM |

### 1.2 Start the Docker stack

```bash
docker compose up -d
```

Wait for all services to be healthy:

```bash
docker compose ps
# All services should show "healthy" or "running"
```

Service startup order matters: Postgres → Redis → MinIO → Langfuse → LiteLLM → Ollama → Qdrant → rag-api → Open WebUI.

### 1.3 Pull the embedding model

```bash
docker compose exec ollama ollama pull nomic-embed-text
```

This is required once per Ollama volume. The model is ~270 MB.

### 1.4 Install Python dependencies

```bash
pip install -r requirements.txt
```

### 1.5 Ingest the corpus

Loads `mock_corpus/`, chunks documents, embeds with Ollama, and stores in Qdrant:

```bash
python -m app.main ingest
```

Expected output:
```
Loading documents...
  Loaded N documents from corpus
Chunking...
  Created N chunks
Embedding and storing in Qdrant...
  Stored N chunks in Qdrant
```

> **Note:** Re-running `ingest` wipes and rebuilds the entire Qdrant collection (`force_recreate=True`). This is intentional — the corpus is the source of truth.

### 1.6 Seed Langfuse (one-time)

Register the RAG system prompt in the Langfuse Prompt Registry:

```bash
python -m scripts.seed_langfuse_prompt
```

Register score config so scores appear in the Langfuse UI:

```bash
python -m scripts.seed_score_configs
```

### 1.7 Configure Open WebUI

1. Open [http://localhost:3100](http://localhost:3100) and create an admin account (first visit only).
2. Select **agentguard-rag** from the model dropdown.
3. Go to **Admin → Functions → Import** and load `config/openwebui/chat_id_injection.json`, then toggle it on and make it **global**
   - This function injects the Open WebUI chat ID into requests for Langfuse session linking.

### 1.8 Verify

```bash
python -m app.main query "What plans does NorthstarCRM offer?"
```

Check Langfuse at [http://localhost:3200](http://localhost:3200) (admin@local.dev / admin123456) — the trace should appear within seconds.

---

## 2. Updating the Knowledge Base Corpus

The corpus lives in `mock_corpus/`. To update it:

### 2.1 Edit or add documents

The loader reads the following file types recursively from `mock_corpus/`:

| Extension | How it's loaded |
|---|---|
| `.md` | Loaded as-is; one Document per file |
| `.jsonl` | One Document per line; each JSON record rendered as `key: value` text |

Supported directory structure:
```
mock_corpus/
├── 01_company/          # .md files
├── 02_products/         # .md files
├── 03_sales_process/    # .md files
├── 04_policies/         # .md files
├── 05_support/          # .md files
├── 06_conversations/    # .jsonl files (conversation examples)
└── 07_benchmark/        # .jsonl files (benchmark questions + labels)
```

### 2.2 Re-ingest

```bash
python -m app.main ingest
```

This rebuilds the Qdrant collection from scratch. Existing vectors are replaced.

### 2.3 Update the system prompt (if needed)

If the domain or tone of the corpus has changed, update the RAG system prompt:

1. Edit `RAG_SYSTEM_PROMPT` in `app/rag/chain.py`.
2. Push a new version to Langfuse:
   ```bash
   python -m scripts.seed_langfuse_prompt --force
   ```
   The new prompt is live within 60 seconds (cache TTL).

### 2.4 Update the agent prompt (if needed)

Edit `AGENT_SYSTEM_PROMPT` in `app/agent/prompts.py`. Restart `rag-api` to pick it up:

```bash
docker compose restart rag-api
```

---

## 3. Switching to a Different Corpus

To swap in an entirely different knowledge base:

1. Place the new corpus directory anywhere on the host.
2. Set `QDRANT_COLLECTION` in `.env` to a new collection name (e.g. `my_corpus`).
3. Run ingest pointing at the new directory:
   ```bash
   python -m app.main ingest
   # or directly:
   python -c "from app.rag.service import ingest; ingest(corpus_dir='path/to/corpus')"
   ```
4. Update the system prompt (§2.3) and agent prompt (§2.4) for the new domain.
5. Re-seed Langfuse prompt:
   ```bash
   python -m scripts.seed_langfuse_prompt --force
   ```

---

## 4. Ongoing Operations

### Background workers

The combined worker runs automatically via the `agentguard-worker` Docker service:

| Worker | Interval | What it does |
|---|---|---|
| `online-eval-worker` | 60s | Evaluates new RAG traces with code-based metrics |
| `feedback-worker` | 120s | Syncs Open WebUI thumbs-up/down to Langfuse scores |
| `dataset-builder` | 300s | Promotes positively rated traces to `rag-golden-set` |

Run manually:
```bash
python -m scripts.worker                        # all three in one process
python -m scripts.online_eval_worker --once     # single eval pass
python -m scripts.sync_feedback --apply         # single feedback sync
python -m scripts.build_dataset                 # build/update golden dataset
```

### Regression gate

Run before any prompt, model, or corpus change to catch regressions:

```bash
python -m app.main regression-gate --dataset rag-golden-set
python -m app.main regression-gate --limit 5   # quick smoke-test
```

Exit codes: `0` = all pass, `1` = metric failure, `2` = runtime error.

### Logs and monitoring

| Tool | URL | Purpose |
|---|---|---|
| Langfuse | http://localhost:3200 | Traces, scores, sessions, prompts, datasets |
| Jaeger | http://localhost:16686 | OpenTelemetry spans (full request lifecycle) |
| Dozzle | http://localhost:8080 | Real-time container logs |
| Portainer | https://localhost:9443 | Container management UI |

---

## 5. Restarting After a Full Stop

```bash
docker compose up -d
# Wait for services to be healthy, then:
python -m app.main query "What is the SLA policy?"
```

Re-ingestion is **not** needed after a restart — Qdrant persists vectors to disk. Only re-ingest if the corpus has changed.

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ingest` fails with connection error | Qdrant not ready | Wait for `docker compose ps` to show Qdrant healthy |
| Embeddings not firing | Ollama model not pulled | `docker compose exec ollama ollama pull nomic-embed-text` |
| RAG returns empty context | Collection name mismatch | Check `QDRANT_COLLECTION` in `.env` matches what was ingested |
| Langfuse prompt not updating | 60s cache TTL | Wait 60s, or restart `rag-api` |
| Open WebUI chat not linked to Langfuse session | Filter not installed | Import `config/openwebui/chat_id_injection.json` in Admin → Functions |
| HTTP 400 on queries with injection patterns | Guardrail firing | Expected — the prompt injection guard is working |
| `curl` from Windows host returns HTTP 000 | AdGuard intercepting | Use Open WebUI at http://localhost:3100 instead |
