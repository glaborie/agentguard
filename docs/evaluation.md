# Evaluation

<!-- markdownlint-disable MD013 MD060 -->

AgentGuard helps teams verify that an AI application still behaves correctly after changes to prompts, models, retrieval logic, or tools.

Instead of waiting for users to discover regressions in production, teams can evaluate known high-risk scenarios in advance and track quality over time.

## Golden datasets

A golden dataset is a curated collection of representative prompts and expected answers that defines what correct behavior looks like for your AI application.

It works like a regression suite for an LLM system. For example, you can include high-risk scenarios such as:

- pricing and discount questions
- refund and policy questions
- compliance-sensitive prompts
- sensitive data handling
- known production failure cases

When you change a prompt, model, retriever, or tool, AgentGuard can run those golden examples again to detect regressions before the change becomes customer-visible.

## Release confidence

This supports release confidence in three ways:

| Capability | What it checks | Why it matters |
|---|---|---|
| **Automated response checks** | Verifies basics such as citation presence, response length, hallucination markers, and output format | Catches simple quality failures before they become user-visible |
| **LLM-based quality review** | Scores answers for relevance, faithfulness, and completeness | Helps assess whether responses are actually useful and grounded |
| **Golden dataset regression testing** | Replays known-good business scenarios across prompts, models, and retrieval changes | Helps prevent silent regressions after system updates |

## Automated response checks (`app/eval/evaluators.py`)

AgentGuard includes deterministic checks for common response-quality issues:

- `has_source_citation` — checks whether the response references a source
- `is_within_length` — enforces a response length limit
- `contains_no_hallucination_markers` — flags hedging language that may indicate weak confidence or unsupported claims
- `is_valid_json` — validates JSON output format when structured output is expected

## LLM-based quality review (`app/eval/evaluators.py`)

AgentGuard also supports model-based review of answer quality using three dimensions:

- **relevance** — does the answer address the question?
- **faithfulness** — is the answer grounded in the retrieved context?
- **completeness** — does the answer cover what the user asked?

## Advanced quality metrics (`app/eval/deepeval_metrics.py`)

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

## RAGAS evaluation for RAG pipelines (`app/eval/ragas_metrics.py`)

AgentGuard also supports [RAGAS](https://github.com/explodinggradients/ragas) for retrieval-focused evaluation.

Use this path when you want metrics that explicitly measure retrieval quality and answer grounding from retrieved context.

| RAGAS metric | What it measures |
|---|---|
| `faithfulness` | Is the answer grounded in retrieved context? |
| `answer_relevancy` | Does the answer address the user question? |
| `context_precision` | How much of retrieved context is relevant? |
| `context_recall` | How much relevant context was retrieved? |
| `answer_correctness` | How accurate is the generated answer vs reference? |

Run RAGAS from the CLI:

```bash
python -m app.main ragas-experiment \
  --dataset watsonx-qa \
  --models openrouter-gemini-flash

python -m app.main ragas-experiment \
  --dataset watsonx-qa \
  --models openrouter-gemini-flash,openrouter-mistral \
  --metrics faithfulness,answer_relevancy \
  --limit 10
```

Notes:

- RAGAS runs in batch per model for better efficiency on larger datasets.
- All judge LLM and embedding calls are routed through LiteLLM, same as the rest of AgentGuard.
- Scores are written back to Langfuse as `ragas_<metric_name>` trace scores.

## Comparing models and configurations (`app/eval/experiments.py`)

AgentGuard can compare multiple models against the same golden dataset so teams can make safer rollout decisions:

```bash
python -m app.main experiment \
  --dataset rag-golden-set \
  --models openrouter-gemini-flash,openrouter-mistral \
  --limit 10
```

## Benchmark suite (`app/eval/benchmark.py`)

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

The benchmark covers questions from `mock_corpus/07_benchmark/`, including standard questions and harder edge cases (competitor-match requests, partial feature overlap, custom legal paper, ambiguous policy interpretation).

## Quality drift monitoring (`app/eval/drift.py`)

AgentGuard tracks metric trends over time and alerts when a metric regresses between consecutive 7-day windows.

| Metric | Regression condition |
|---|---|
| `faithfulness` | Current window mean drops > 0.05 vs prior window |
| `answer_relevancy` | Current window mean drops > 0.05 vs prior window |
| `contextual_relevancy` | Current window mean drops > 0.05 vs prior window |
| `hallucination` | Current window mean rises > 0.05 vs prior window (higher = worse) |

Run from the CLI against real Langfuse score history:

```bash
# Report only
python -m app.main drift-check

# Exit 1 if any regression detected (suitable for CI)
python -m app.main drift-check --fail-on-regression

# Custom history window and per-metric threshold overrides
python -m app.main drift-check --days 30 --threshold faithfulness=0.03 --threshold hallucination=0.02
```

For exploratory analysis, open `notebooks/quality_drift.ipynb`. Set `USE_SYNTHETIC_DATA = True` on fresh installs (fewer than 14 days of real Langfuse scores) to see the full trend visualization with synthetic data.

The core logic lives in `app/eval/drift.py`:

- `check_drift(scores: pd.DataFrame, threshold_overrides=None) -> list[DriftAlert]` — pure function, takes a DataFrame, returns alerts. No Langfuse dependency; easy to test and import from CI.
- `fetch_scores_from_langfuse(days=14) -> pd.DataFrame` — fetches scores from Langfuse and returns the DataFrame that `check_drift` expects.
- `DriftAlert` — dataclass with `metric`, `baseline_mean`, `current_mean`, `delta`, `threshold`, `status`.
