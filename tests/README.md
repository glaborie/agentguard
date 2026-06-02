# Tests

## Running tests

```bash
# Unit tests only — no Docker needed (~5s)
pytest -m "not integration"

# Integration tests — requires Docker stack running (see below)
pytest -m integration

# Full suite
pytest -v

# Single file
pytest tests/test_guardrails.py -v
```

## Test inventory

| File | Tests | What it covers |
|------|-------|----------------|
| `test_agent_tools.py` | 22 | All 5 agent tool functions |
| `test_agent_graph.py` | 13 | LangGraph structure, routing, prompts |
| `test_deepeval_metrics.py` | 14 | LiteLLM model wrapper, DeepEval metric factories |
| `test_guardrails.py` | 43 | Injection detection patterns, PII masking |
| `test_evaluators.py` | 16 | Code-based evaluators |
| `test_config.py` | 3 | Settings defaults and env overrides |
| `test_chain.py` | 9 | `format_docs`, prompt wiring, e2e RAG query |
| `test_ingest.py` | 21 | Corpus loader (md, jsonl, recursive, source path) |
| `test_cli.py` | 29 | Parser recognition, dispatch, session/user flags |
| `test_services.py` | 35 | Service error mapping and flow logic |
| `test_api_routes.py` | 16 | Route handlers (auto-skipped without fastapi) |
| `test_benchmark.py` | 38 | Loaders, retrieval hit, factual coverage, escalation, CLI |
| `test_regression_gate.py` | — | Regression gate threshold logic |
| `test_agent_integration.py` | 5 | Agent e2e — **requires Docker** |
| `test_integration.py` | 8 | Service health, RAG API, guardrails e2e — **requires Docker** |

## Docker dependency

Integration tests (`-m integration`) hit live services and require the full stack:

```bash
docker compose up -d
```

Required services: LiteLLM on `localhost:4000`, Langfuse on `localhost:3000`, Qdrant on `localhost:6333`.

`conftest.py` probes `http://localhost:4000/health/liveliness` at collection time. If the stack is unreachable, all integration tests are **auto-skipped** — they will not fail, just skip. No manual flag needed.
