# Reliability and Quality Evidence

## Purpose

This document provides concrete technical evidence that AgentGuard is built and operated with production-style quality controls.

It is intentionally framed as an API-first, enterprise-integrated reliability platform.

## API-first evidence

| API-centric design choice | Evidence |
|---|---|
| OpenAI-compatible integration surface | `README.md`, `app/api/routes/chat.py`, `app/api/services/chat_service.py` |
| Gateway-based model abstraction | `litellm_config.yaml`, `docker-compose.yml`, `app/rag/chain.py` |
| Operational CLI as quality API | `app/cli/commands/evaluate.py`, `app/cli/commands/regression.py`, `app/cli/commands/drift.py` |

## Enterprise integration evidence

| Integration | Evidence | Enterprise value |
|---|---|---|
| LiteLLM | `litellm_config.yaml`, `docker-compose.litellm.yml` | Multi-provider model routing via stable interface |
| Langfuse | `app/core/tracing.py`, `scripts/sync_feedback.py` | Auditability, score history, and trace-linked operations |
| OpenTelemetry | `app/core/telemetry.py`, `otel-collector-config.yaml` | Interoperable telemetry and incident diagnostics |
| Arize AX | `litellm_config.yaml` callbacks, docs references | External quality analytics and observability portability |
| Open WebUI/API | `app/api/routes/*.py`, `README.md` | Fast adoption path for internal business teams |

## Reliability control layers

| Layer | Mechanism | Evidence in repository |
|---|---|---|
| Prevention | Prompt-injection checks, toxicity checks, PII masking, tool-call guards | `guardrails/custom_guardrails.py`, `app/agent/tool_guard.py` |
| Detection | Traces, score streams, telemetry fan-out, log analytics | `app/core/tracing.py`, `app/core/telemetry.py`, `otel-collector-config.yaml` |
| Verification | Deterministic evaluators, DeepEval, RAGAS, benchmark suite | `app/eval/evaluators.py`, `app/eval/deepeval_metrics.py`, `app/eval/ragas_metrics.py`, `app/eval/benchmark.py` |
| Regression control | Regression gate and drift checks | `app/eval/service.py`, `app/eval/drift.py` |
| Feedback loop | User rating sync, online eval worker, dataset builder | `scripts/sync_feedback.py`, `scripts/online_eval_worker.py`, `scripts/build_dataset.py` |

## Risk management and mitigation matrix

| Risk scenario | Likely failure mode | Mitigation in platform | Validation path |
|---|---|---|---|
| Prompt injection attempts | Model instruction override | Pre-call injection guards | `tests/test_guardrails.py`, red-team commands |
| Sensitive data leakage | PII in generated output | Post-call PII masking | `tests/test_guardrails.py`, integration checks |
| Unsafe autonomous tool actions | Unbounded or malicious tool arguments | Tool-call guardrail + argument validation | `tests/test_agent_tool_guard.py` |
| Silent quality degradation | Lower answer faithfulness/relevance | DeepEval/RAGAS + regression gate + drift check | `tests/test_regression_gate.py`, `tests/test_drift.py` |
| Poor incident diagnosability | Missing request context and lineage | Trace + telemetry fan-out architecture | Langfuse/OTel workflow and service tracing |

## Test coverage signal by domain

| Domain | Representative test files | Reliability objective |
|---|---|---|
| Guardrails | `tests/test_guardrails.py`, `tests/test_agent_tool_guard.py` | Block unsafe inputs and unsafe tool usage |
| Agent behavior | `tests/test_agent_graph.py`, `tests/test_agent_tools.py`, `tests/test_agent_llm.py` | Ensure stable agent routing and tool invocation |
| Evaluation | `tests/test_evaluators.py`, `tests/test_deepeval_metrics.py`, `tests/test_experiments.py`, `tests/test_regression_gate.py`, `tests/test_drift.py` | Keep scoring and release gates consistent across changes |
| Retrieval/RAG | `tests/test_chain.py`, `tests/test_ingest.py`, `tests/test_hybrid_retriever.py`, `tests/test_bm25_index.py` | Preserve retrieval quality and ingestion correctness |
| Service/API integration | `tests/test_services.py`, `tests/test_api_routes.py`, `tests/test_integration.py`, `tests/test_agent_integration.py` | Validate external behavior and runtime contracts |

## Operating commands (interview-demo ready)

Use these commands to demonstrate quality controls in a short live walkthrough:

```bash
# Core test suites
make test

# Fast unit pass
pytest -m "not integration"

# Integration validation (requires stack)
pytest -m integration

# Regression gate example
python -m app.main regression-gate --dataset rag-golden-set --limit 5

# Drift check example
python -m app.main drift-check --fail-on-regression

# RAGAS evaluation example
python -m app.main ragas-experiment --dataset watsonx-qa --models openrouter-gemini-flash --limit 10

# Red-team smoke run
python -m app.main red-team --limit 3
```

## Timeline evidence of quality hardening

| Reliability concern | Action | Commits |
|---|---|---|
| RAGAS provider mismatch risk | Forced `n=1`, stabilized evaluate return handling | `92ced66`, `4e2294c` |
| Regression risk from eval changes | Added targeted test coverage and model count assertion fixes | `f170243` |
| Docs drift as operational risk | Consolidated deployment docs and conventions, removed stale plan/status artifacts | `28e6596`, `fba3840` |
| Runtime and observability control expansion | Added drift monitoring and observability stack components | `7d6a001`, `a9fa941` |

## Recruiter translation points

- This project includes API platform delivery, enterprise integration work, and risk control implementation, which is a strong signal for production engineering maturity.
- Quality controls are implemented as repeatable workflows (tests + CLI gates), not just one-off checks.
- Git history shows iterative hardening: detect issue, patch safely, add tests, document behavior.

## One-paragraph technical recruiter summary

AgentGuard demonstrates end-to-end ownership of API-first AI reliability engineering: enterprise-ready integrations, runtime safety controls, observability and evaluation pipelines, and regression gates backed by tests. The commit trail shows a consistent engineering loop of shipping capabilities, hardening edge cases, and reducing operational/documentation drift.
