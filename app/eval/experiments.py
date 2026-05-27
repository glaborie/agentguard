"""Multi-model experiment runner: compare RAG variants against a Langfuse dataset."""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from deepeval.test_case import LLMTestCase

from app.eval.deepeval_metrics import get_metrics
from app.rag.chain import get_retriever, query
from app.tracing import get_langfuse_client, get_langfuse_handler

logger = logging.getLogger(__name__)


@dataclass
class ItemResult:
    question: str
    model: str
    output: str
    scores: dict[str, float] = field(default_factory=dict)
    trace_id: str | None = None


def run_experiment(
    dataset_name: str,
    models: list[str],
    run_prefix: str = "experiment",
    metric_names: list[str] | None = None,
    judge_model: str | None = None,
) -> tuple[list[ItemResult], dict[str, str]]:
    """Run every model against every dataset item and push results to Langfuse.

    Each model gets its own named dataset run so the Langfuse Datasets UI
    shows a per-model comparison in the Runs tab. DeepEval scores are pushed
    back as trace scores and appear in the run detail view.

    Returns:
        (results, run_names) — run_names maps model name → Langfuse run name.
    """
    from app.config import settings

    judge = judge_model or settings.deepeval_model or settings.default_model
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")

    client = get_langfuse_client()
    dataset = client.get_dataset(dataset_name)
    retriever = get_retriever(k=6)

    run_names = {
        model: f"{run_prefix}-{model}-{timestamp}"
        for model in models
    }

    results: list[ItemResult] = []
    total = len(dataset.items) * len(models)
    done = 0

    for item in dataset.items:
        question = (
            item.input.get("question", str(item.input))
            if isinstance(item.input, dict)
            else str(item.input)
        )
        expected = str(item.expected_output) if item.expected_output else None

        # Retrieve context once per question — same for all models.
        docs = retriever.invoke(question)
        retrieval_context = [doc.page_content for doc in docs]

        for model_name in models:
            done += 1
            run_name = run_names[model_name]
            logger.info("[%d/%d] model=%-30s  q=%s...", done, total, model_name, question[:50])

            # ── Generate answer ───────────────────────────────────────────────
            handler = get_langfuse_handler()
            output = query(question=question, model=model_name, callbacks=[handler])
            trace_id = handler.last_trace_id

            # ── DeepEval metrics ──────────────────────────────────────────────
            metrics = get_metrics(names=metric_names, model=judge)
            test_case = LLMTestCase(
                input=question,
                actual_output=output,
                expected_output=expected,
                retrieval_context=retrieval_context,
            )

            item_scores: dict[str, float] = {}
            for metric in metrics:
                metric_label = type(metric).__name__
                try:
                    metric.measure(test_case)
                    score = float(metric.score)
                    item_scores[metric_label] = score
                    reason = (getattr(metric, "reason", "") or "")[:500]
                    logger.info("  %-30s %.2f  %s", metric_label, score, reason[:60])

                    if trace_id:
                        client.create_score(
                            trace_id=trace_id,
                            name=f"deepeval_{metric_label.lower()}",
                            value=score,
                            data_type="NUMERIC",
                            comment=reason or None,
                        )
                except Exception as exc:
                    logger.warning("  %s FAILED: %s", metric_label, exc)

            # ── Link trace to the model's dataset run ─────────────────────────
            if trace_id:
                try:
                    client.api.dataset_run_items.create(
                        run_name=run_name,
                        dataset_item_id=item.id,
                        trace_id=trace_id,
                    )
                except Exception as exc:
                    logger.warning("dataset_run_items.create failed: %s", exc)

            results.append(ItemResult(
                question=question,
                model=model_name,
                output=output,
                scores=item_scores,
                trace_id=trace_id,
            ))

    client.flush()
    return results, run_names


def print_comparison_table(
    results: list[ItemResult],
    run_names: dict[str, str],
    dataset_name: str,
) -> None:
    """Print a per-model average score table to stdout."""
    models = list(run_names.keys())

    # Collect metric names in insertion order.
    metric_names: list[str] = []
    for r in results:
        for k in r.scores:
            if k not in metric_names:
                metric_names.append(k)

    # Aggregate per model and metric.
    agg: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        for metric, score in r.scores.items():
            agg[r.model][metric].append(score)

    avgs: dict[str, dict[str, float]] = {
        model: {
            m: (sum(agg[model][m]) / len(agg[model][m])) if agg[model][m] else float("nan")
            for m in metric_names
        }
        for model in models
    }

    # Strip "openrouter-" prefix for column headers.
    display_names = {
        m: (m.split("-", 1)[-1] if m.startswith("openrouter-") else m)
        for m in models
    }
    label_w = max((len(m) for m in metric_names), default=10) + 2
    col_w = max(max(len(d) for d in display_names.values()) + 2, 10)
    sep = "─" * (label_w + col_w * len(models) + 2)

    n_items = len(results) // max(len(models), 1)
    print(f"\n{'═' * (len(sep) + 2)}")
    print(f"  Experiment  : {dataset_name}")
    print(f"  Run at      : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Evaluations : {len(results)}  ({n_items} items × {len(models)} models)")
    print(f"  {sep}")

    header = f"  {'Metric':<{label_w}}"
    for m in models:
        header += f"{display_names[m]:>{col_w}}"
    print(header)
    print(f"  {sep}")

    for metric in metric_names:
        row = f"  {metric:<{label_w}}"
        for m in models:
            v = avgs[m].get(metric, float("nan"))
            row += f"{v:>{col_w}.2f}"
        print(row)

    print(f"  {sep}")
    row = f"  {'AVERAGE':<{label_w}}"
    for m in models:
        all_scores = [s for scores in agg[m].values() for s in scores]
        overall = sum(all_scores) / len(all_scores) if all_scores else float("nan")
        row += f"{overall:>{col_w}.2f}"
    print(row)

    print(f"  {sep}")
    print("  Langfuse dataset runs:")
    for m, run_name in run_names.items():
        print(f"    {run_name}")
    print(f"{'═' * (len(sep) + 2)}\n")
