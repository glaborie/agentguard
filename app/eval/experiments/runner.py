"""Multi-model experiment runners (DeepEval and RAGAS)."""

from __future__ import annotations

import logging
from datetime import datetime

from deepeval.test_case import LLMTestCase
from langfuse import propagate_attributes

from app.core.config import settings
from app.core.tracing import get_langfuse_client, get_langfuse_handler
from app.eval.deepeval_metrics import get_metrics
from app.eval.experiments.items import ItemResult
from app.rag.chain import get_retriever, query_with_usage

logger = logging.getLogger(__name__)


def run_experiment(
    dataset_name: str,
    models: list[str],
    run_prefix: str = "experiment",
    metric_names: list[str] | None = None,
    judge_model: str | None = None,
    limit: int | None = None,
) -> tuple[list[ItemResult], dict[str, str]]:
    """Run every model against every dataset item and push results to Langfuse.

    Each model gets its own named dataset run so the Langfuse Datasets UI
    shows a per-model comparison in the Runs tab. DeepEval scores are pushed
    back as trace scores and appear in the run detail view.

    Returns:
        (results, run_names) — run_names maps model name → Langfuse run name.
    """
    judge = judge_model or settings.deepeval_model or settings.default_model
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")

    client = get_langfuse_client()
    dataset = client.get_dataset(dataset_name)
    items = dataset.items[:limit] if limit else dataset.items
    retriever = get_retriever(k=6)

    run_names = {
        model: f"{run_prefix}-{model}-{timestamp}"
        for model in models
    }

    results: list[ItemResult] = []
    total = len(items) * len(models)
    done = 0

    for item in items:
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
            with propagate_attributes(trace_name="eval-experiment", tags=["eval", "experiment"]):
                output, usage = query_with_usage(question=question, model=model_name, callbacks=[handler])
            trace_id = handler.last_trace_id

            # ── DeepEval metrics ──────────────────────────────────────────────
            metrics = get_metrics(names=metric_names, model=judge)
            test_case = LLMTestCase(
                input=question,
                actual_output=output,
                expected_output=expected,
                retrieval_context=retrieval_context,
                context=retrieval_context,
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

            # ── Push cost score to Langfuse ───────────────────────────────────
            if trace_id and usage.get("total_tokens"):
                try:
                    client.create_score(
                        trace_id=trace_id,
                        name="cost_usd_milli",
                        value=round(float(usage["cost_usd"]) * 1000, 4),
                        data_type="NUMERIC",
                        comment=f"cost=${usage['cost_usd']:.6f} prompt={usage['prompt_tokens']} completion={usage['completion_tokens']}",
                    )
                except Exception as exc:
                    logger.warning("cost score push failed: %s", exc)

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
                prompt_tokens=int(usage["prompt_tokens"]),
                completion_tokens=int(usage["completion_tokens"]),
                total_tokens=int(usage["total_tokens"]),
                cost_usd=float(usage["cost_usd"]),
            ))

    client.flush()
    return results, run_names


def run_ragas_experiment(
    dataset_name: str,
    models: list[str],
    run_prefix: str = "ragas-experiment",
    metric_names: list[str] | None = None,
    judge_model: str | None = None,
    limit: int | None = None,
) -> tuple[list[ItemResult], dict[str, str]]:
    """Like run_experiment() but scores with RAGAS instead of DeepEval.

    RAGAS evaluate() runs on the full batch per model (more efficient than
    per-item metric.measure()), so scores are collected after generation
    then pushed back to Langfuse.
    """
    from app.eval.ragas_metrics import ALL_METRICS, build_ragas_dataset, run_ragas_evaluation

    judge = judge_model or settings.ragas_model or settings.default_model
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")

    client = get_langfuse_client()
    dataset = client.get_dataset(dataset_name)
    items = dataset.items[:limit] if limit else dataset.items
    retriever = get_retriever(k=6)

    names = metric_names or ALL_METRICS
    run_names = {model: f"{run_prefix}-{model}-{timestamp}" for model in models}
    results: list[ItemResult] = []

    for model_name in models:
        run_name = run_names[model_name]
        logger.info("Model: %s  |  dataset: %s  |  items: %d", model_name, dataset_name, len(items))

        questions: list[str] = []
        generated: list[str] = []
        contexts: list[list[str]] = []
        ground_truths: list[str] = []
        trace_ids: list[str | None] = []
        usages: list[dict] = []

        for i, item in enumerate(items):
            question = (
                item.input.get("question", str(item.input))
                if isinstance(item.input, dict)
                else str(item.input)
            )
            expected = str(item.expected_output) if item.expected_output else ""
            logger.info("  [%d/%d] %s …", i + 1, len(items), question[:60])

            docs = retriever.invoke(question)
            retrieval_context = [doc.page_content for doc in docs]

            handler = get_langfuse_handler()
            with propagate_attributes(trace_name="ragas-experiment", tags=["eval", "ragas"]):
                output, usage = query_with_usage(question=question, model=model_name, callbacks=[handler])

            questions.append(question)
            generated.append(output)
            contexts.append(retrieval_context)
            ground_truths.append(expected)
            trace_ids.append(handler.last_trace_id)
            usages.append(usage)

        # ── Batch RAGAS evaluation ─────────────────────────────────────────
        ragas_ds = build_ragas_dataset(questions, generated, contexts, ground_truths or None)
        scores_list = run_ragas_evaluation(ragas_ds, metric_names=names, model=judge)

        for i, item in enumerate(items):
            item_scores = scores_list[i] if i < len(scores_list) else {}
            trace_id = trace_ids[i]
            usage = usages[i]

            for metric_name, score in item_scores.items():
                if score is None:
                    continue
                logger.info("  %-30s %.3f", metric_name, score)
                if trace_id:
                    try:
                        client.create_score(
                            trace_id=trace_id,
                            name=f"ragas_{metric_name}",
                            value=float(score),
                            data_type="NUMERIC",
                        )
                    except Exception as exc:
                        logger.warning("score push failed: %s", exc)

            if trace_id and usage.get("total_tokens"):
                try:
                    client.create_score(
                        trace_id=trace_id,
                        name="cost_usd_milli",
                        value=round(float(usage["cost_usd"]) * 1000, 4),
                        data_type="NUMERIC",
                        comment=f"cost=${usage['cost_usd']:.6f} prompt={usage['prompt_tokens']} completion={usage['completion_tokens']}",
                    )
                except Exception as exc:
                    logger.warning("cost score push failed: %s", exc)

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
                question=questions[i],
                model=model_name,
                output=generated[i],
                scores=item_scores,
                trace_id=trace_id,
                prompt_tokens=int(usage["prompt_tokens"]),
                completion_tokens=int(usage["completion_tokens"]),
                total_tokens=int(usage["total_tokens"]),
                cost_usd=float(usage["cost_usd"]),
            ))

    client.flush()
    return results, run_names
