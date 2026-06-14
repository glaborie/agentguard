"""Automated regression gate for the RAG golden dataset.

Runs every item in a Langfuse dataset through the RAG chain, evaluates with
DeepEval, and exits non-zero if any metric average falls outside its threshold.

Exit codes:
  0  all metrics passed
  1  one or more metrics failed threshold
  2  configuration or runtime error

Usage:
  python -m scripts.regression_gate                          # all items, defaults
  python -m scripts.regression_gate --limit 5               # quick smoke-test
  python -m scripts.regression_gate --thresholds '{"FaithfulnessMetric": 0.90}'
  python -m app.main regression-gate --limit 5              # via main CLI
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime

from deepeval.test_case import LLMTestCase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# HallucinationMetric scores 0-1 where 0 = no hallucination.
# Threshold is a MAXIMUM — gate fails if avg EXCEEDS it.
LOWER_IS_BETTER = {"HallucinationMetric"}

DEFAULT_THRESHOLDS: dict[str, float] = {
    "FaithfulnessMetric": 0.80,
    "AnswerRelevancyMetric": 0.70,
    "ContextualRelevancyMetric": 0.30,
    "HallucinationMetric": 0.30,
}


def run_gate(
    dataset_name: str,
    model: str | None = None,
    metric_names: list[str] | None = None,
    thresholds: dict[str, float] | None = None,
    limit: int | None = None,
    judge_model: str | None = None,
    run_prefix: str = "regression-gate",
    push_scores: bool = True,
) -> bool:
    """Evaluate the dataset and check thresholds. Returns True if all pass."""
    from app.core.config import settings
    from app.eval.deepeval_metrics import get_metrics
    from app.rag.chain import get_retriever, query
    from app.core.tracing import get_langfuse_client, get_langfuse_handler

    effective_thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    judge = judge_model or settings.deepeval_model or settings.default_model
    effective_model = model or settings.default_model
    run_name = f"{run_prefix}-{datetime.now().strftime('%Y%m%d-%H%M')}"

    client = get_langfuse_client()
    dataset = client.get_dataset(dataset_name)
    items = dataset.items[:limit] if limit else dataset.items

    if not items:
        logger.error("Dataset '%s' is empty.", dataset_name)
        return False

    logger.info(
        "Regression gate: dataset=%s  model=%s  items=%d  judge=%s",
        dataset_name, effective_model, len(items), judge,
    )

    retriever = get_retriever(k=6)
    metrics_objs = get_metrics(names=metric_names, model=judge)
    metric_labels = [type(m).__name__ for m in metrics_objs]
    scores_by_metric: dict[str, list[float]] = defaultdict(list)

    for idx, item in enumerate(items, 1):
        question = (
            item.input.get("question", str(item.input))
            if isinstance(item.input, dict)
            else str(item.input)
        )
        expected = str(item.expected_output) if item.expected_output else None
        logger.info("[%d/%d] %s...", idx, len(items), question[:60])

        docs = retriever.invoke(question)
        retrieval_context = [doc.page_content for doc in docs]

        handler = get_langfuse_handler()
        output = query(question=question, model=effective_model, callbacks=[handler])
        trace_id = handler.last_trace_id

        test_case = LLMTestCase(
            input=question,
            actual_output=output,
            expected_output=expected,
            retrieval_context=retrieval_context,
            context=retrieval_context,
        )

        for metric_obj, label in zip(metrics_objs, metric_labels):
            try:
                metric_obj.measure(test_case)
                score = float(metric_obj.score)
                scores_by_metric[label].append(score)
                reason = (getattr(metric_obj, "reason", "") or "")[:500]
                logger.info("  %-30s %.3f  %s", label, score, reason[:60])

                if push_scores and trace_id:
                    client.create_score(
                        trace_id=trace_id,
                        name=f"gate_{label.lower()}",
                        value=score,
                        data_type="NUMERIC",
                        comment=reason or None,
                    )
            except Exception as exc:
                logger.warning("  %s FAILED: %s", label, exc)

        if push_scores and trace_id:
            try:
                client.api.dataset_run_items.create(
                    run_name=run_name,
                    dataset_item_id=item.id,
                    trace_id=trace_id,
                )
            except Exception as exc:
                logger.warning("dataset_run_items.create failed: %s", exc)

    client.flush()

    avgs = {
        label: (sum(vals) / len(vals) if vals else float("nan"))
        for label, vals in scores_by_metric.items()
    }
    failures = _check_thresholds(avgs, effective_thresholds)
    _print_report(dataset_name, effective_model, run_name, len(items),
                  avgs, effective_thresholds, failures, metric_labels)
    return len(failures) == 0


def _check_thresholds(
    avgs: dict[str, float], thresholds: dict[str, float]
) -> list[str]:
    failures = []
    for label, avg in avgs.items():
        threshold = thresholds.get(label)
        if threshold is None:
            continue
        if label in LOWER_IS_BETTER:
            if avg > threshold:
                failures.append(f"{label}: {avg:.3f} > {threshold:.2f} (max allowed)")
        else:
            if avg < threshold:
                failures.append(f"{label}: {avg:.3f} < {threshold:.2f} (min required)")
    return failures


def _print_report(
    dataset_name: str,
    model: str,
    run_name: str,
    n_items: int,
    avgs: dict[str, float],
    thresholds: dict[str, float],
    failures: list[str],
    metric_labels: list[str],
) -> None:
    col_w = max((len(m) for m in metric_labels), default=10) + 2
    sep = "-" * (col_w + 36)

    print(f"\n{'=' * (len(sep) + 2)}")
    print(f"  Regression Gate  : {dataset_name}")
    print(f"  Model            : {model}")
    print(f"  Run at           : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Items evaluated  : {n_items}")
    print(f"  Langfuse run     : {run_name}")
    print(f"  {sep}")
    print(f"  {'Metric':<{col_w}} {'Avg':>7}  {'Threshold':>12}  {'Status':>6}")
    print(f"  {sep}")

    for label in metric_labels:
        avg = avgs.get(label, float("nan"))
        threshold = thresholds.get(label, float("nan"))
        if label in LOWER_IS_BETTER:
            threshold_str = f"<= {threshold:.2f}"
            passed = avg <= threshold
        else:
            threshold_str = f">= {threshold:.2f}"
            passed = avg >= threshold
        status = "PASS" if passed else "FAIL"
        print(f"  {label:<{col_w}} {avg:>7.3f}  {threshold_str:>12}  {status:>6}")

    print(f"  {sep}")
    if failures:
        print(f"\n  GATE FAILED  ({len(failures)} metric(s) out of range):")
        for msg in failures:
            print(f"    - {msg}")
    else:
        print(f"\n  GATE PASSED  - all metrics within thresholds")
    print(f"{'=' * (len(sep) + 2)}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regression gate: fail if metric averages drop below thresholds."
    )
    parser.add_argument("--dataset", default="rag-golden-set",
                        help="Langfuse dataset name (default: rag-golden-set)")
    parser.add_argument("--model", default=None,
                        help="RAG model (default: settings.default_model)")
    parser.add_argument("--metrics", default=None,
                        help="Comma-separated metric names (default: all)")
    parser.add_argument("--judge-model", default=None,
                        help="DeepEval judge model (default: settings.deepeval_model)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max dataset items (default: all)")
    parser.add_argument("--thresholds", default=None,
                        help='JSON overrides e.g. \'{"FaithfulnessMetric":0.85}\'')
    parser.add_argument("--run-prefix", default="regression-gate",
                        help="Langfuse run name prefix (default: regression-gate)")
    parser.add_argument("--no-push", action="store_true",
                        help="Skip pushing scores to Langfuse")
    args = parser.parse_args()

    metric_names = [m.strip() for m in args.metrics.split(",")] if args.metrics else None
    thresholds = json.loads(args.thresholds) if args.thresholds else None

    try:
        passed = run_gate(
            dataset_name=args.dataset,
            model=args.model,
            metric_names=metric_names,
            thresholds=thresholds,
            limit=args.limit,
            judge_model=args.judge_model,
            run_prefix=args.run_prefix,
            push_scores=not args.no_push,
        )
    except Exception as exc:
        logger.error("Gate error: %s", exc, exc_info=True)
        sys.exit(2)

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
