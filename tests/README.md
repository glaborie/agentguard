# Tests

## Quick start

```bash
# Unit tests only — no Docker needed (~5s)
pytest -m "not integration"

# Unit tests with coverage report
pytest -m "not integration" --cov=app --cov=guardrails --cov-report=term-missing

# Integration tests — requires live Docker stack (see below)
pytest -m integration

# Full suite (unit + integration)
pytest -v
```

## Make targets

The `Makefile` provides convenience aliases. Run `make help` to see them all.

| Target | What it runs |
|---|---|
| `make test` | All unit tests, verbose |
| `make test-cov` | Unit tests with coverage report |
| `make test-all` | Full suite (unit + integration) |
| `make test-all-cov` | Full suite with coverage report |
| `make test-fast` | Unit tests in parallel, minimal output (needs `pytest-xdist`) |
| `make test-agent` | Agent graph, tools, tool guard, LLM, integration |
| `make test-rag` | Chain, ingest, hybrid retriever, BM25 |
| `make test-api` | API routes and services |
| `make test-eval` | Evaluators, DeepEval, regression gate, benchmark |
| `make test-drift` | Quality drift detection |
| `make test-guardrails` | Guardrail patterns and semantic cache |
| `make test-cli` | CLI parser and dispatch |
| `make test-red-team` | Adversarial red team scenarios |
| `make test-integration-end-to-end` | End-to-end integration tests |
| `make test-config` | Config/settings defaults |
| `make test-file FILE=tests/test_chain.py` | Single file |
| `make test-k K=retriever` | Tests matching a keyword |

## Test inventory

### Unit tests (no Docker required)

| File | Tests | What it covers |
|------|-------|----------------|
| `test_agent_graph.py` | 13 | LangGraph structure, node routing, prompts |
| `test_agent_llm.py` | 9 | Model registry — agent and RAG model name constants |
| `test_agent_tool_guard.py` | 23 | Tool-call guardrail — unknown tools, injection-shaped args, known-tool passthrough |
| `test_agent_tools.py` | 22 | All 5 agent tool functions (doc search, trace list/detail, score, dataset) |
| `test_api_routes.py` | 16 | Route handlers for chat, models, config, retrieval debug |
| `test_benchmark.py` | 38 | Benchmark loaders, retrieval hit rate, factual coverage, escalation detection, CLI |
| `test_bm25_index.py` | 11 | BM25 index build, cache hit/miss, chunk-count and collection-name invalidation |
| `test_bm25_warmup.py` | — | BM25 warmup script (fixture-only, no assertions) |
| `test_chain.py` | 9 | `format_docs`, prompt wiring, e2e RAG query |
| `test_cli.py` | 29 | Parser recognition, subcommand dispatch, flag wiring |
| `test_config.py` | 3 | Settings defaults and env var overrides |
| `test_deepeval_metrics.py` | 14 | LiteLLM model wrapper, DeepEval metric factory functions |
| `test_drift.py` | 9 | Drift detection — stable, improving, regression, and multi-metric alerting |
| `test_evaluators.py` | 16 | Code-based evaluators (citation, length, hallucination markers, JSON) |
| `test_experiments.py` | 7 | Multi-model experiment runner — aggregation, cost tracking, result shape |
| `test_guardrails.py` | 43 | Injection regex patterns, semantic guard, PII masking |
| `test_hybrid_retriever.py` | 12 | Hybrid retriever construction, top-k, deduplication, OTel attributes |
| `test_ingest.py` | 21 | Corpus loader — `.md`, `.jsonl`, recursive dirs, source path metadata |
| `test_red_team.py` | 13 | Red team runner — pass/fail scoring, HTTP 400/403 blocking logic |
| `test_regression_gate.py` | 15 | Regression gate threshold evaluation and exit-code logic |
| `test_semantic_cache.py` | 6 | Cache key normalisation, multi-turn messages, LiteLLM cache integration |
| `test_services.py` | 35 | Service layer error mapping and flow logic |

### Integration tests (requires Docker stack)

| File | Tests | What it covers |
|------|-------|----------------|
| `test_agent_integration.py` | 5 | Agent e2e — tool invocation over live stack |
| `test_integration.py` | 15 | Service health, RAG API end-to-end, guardrail enforcement |

## Docker dependency

Integration tests (`-m integration`) hit live services:

```bash
docker compose up -d
```

Required services:

| Service | Host port |
|---|---|
| LiteLLM | `localhost:4000` |
| Langfuse | `localhost:3200` |
| Qdrant | `localhost:6333` |

`conftest.py` probes `http://localhost:4000/health/liveliness` at collection time. If the stack is unreachable, all integration tests are **auto-skipped** — they will not fail, just skip. No manual flag needed.

## Mocking approach

- `test_guardrails.py` — mocks the entire `litellm` module hierarchy via `sys.modules` because LiteLLM only runs inside the Docker container.
- `test_api_routes.py` — uses `__getattr__` lazy-loading in `app/api/__init__.py` so importing API services in unit tests does not require FastAPI to be importable.
- `test_chain.py` and `test_ingest.py` — patch Qdrant and Ollama clients; no network calls.
- `test_drift.py` — passes synthetic DataFrames directly to `check_drift()` (pure function), no Langfuse dependency.
