"""DeepEval evaluation runner that bridges DeepEval metrics with Langfuse."""

from deepeval.test_case import LLMTestCase

from app.core.config import settings
from app.core.tracing import get_callbacks, get_langfuse_client, get_langfuse_handler
from app.eval.deepeval_metrics import get_metrics
from app.rag.chain import get_retriever, query_with_usage


def run_deepeval_evaluation(
    dataset_name: str,
    metric_names: list[str] | None = None,
    model: str | None = None,
    cost_report: bool = False,
) -> None:
    """Run DeepEval metrics against a Langfuse dataset and push scores back.

    Args:
        dataset_name: Name of the Langfuse dataset.
        metric_names: Which metrics to run (None = all).
        model: Override model for both generation and judge.
    """
    # Default to deepeval_model for both generation and judge so the evaluate
    # command doesn't fall back to the local Ollama default.
    model = model or settings.deepeval_model or settings.default_model

    client = get_langfuse_client()
    dataset = client.get_dataset(dataset_name)
    metrics = get_metrics(names=metric_names, model=model)

    if not metrics:
        print("No valid metrics selected.")
        return

    print(f"Dataset: {dataset_name}")
    print(f"Metrics: {[type(m).__name__ for m in metrics]}")
    print(f"Items:   {len(dataset.items)}\n")

    retriever = get_retriever(k=6)
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_cost_usd = 0.0

    for i, item in enumerate(dataset.items):
        question = item.input.get("question", str(item.input)) if isinstance(item.input, dict) else str(item.input)
        expected = str(item.expected_output) if item.expected_output else None

        print(f"[{i+1}/{len(dataset.items)}] {question[:80]}...")

        handler = get_langfuse_handler()
        output, usage = query_with_usage(question=question, model=model, callbacks=get_callbacks())
        total_prompt_tokens += int(usage.get("prompt_tokens", 0))
        total_completion_tokens += int(usage.get("completion_tokens", 0))
        total_cost_usd += float(usage.get("cost_usd", 0.0))

        docs = retriever.invoke(question)
        retrieval_context = [doc.page_content for doc in docs]

        test_case = LLMTestCase(
            input=question,
            actual_output=output,
            expected_output=expected,
            retrieval_context=retrieval_context,
        )

        for metric in metrics:
            try:
                metric.measure(test_case)
                score_value = metric.score
                reason = metric.reason if hasattr(metric, "reason") else ""
                metric_name = type(metric).__name__

                print(f"  {metric_name}: {score_value:.2f}" + (f" — {reason[:80]}" if reason else ""))

                client.create_score(
                    name=f"deepeval_{metric_name.lower()}",
                    value=score_value,
                    data_type="NUMERIC",
                    comment=reason[:500] if reason else None,
                    trace_id=handler.trace_id if hasattr(handler, "trace_id") else None,
                )
            except Exception as e:
                print(f"  {type(metric).__name__}: ERROR — {e}")

    client.flush()
    print(f"\nDone. Scores pushed to Langfuse for {len(dataset.items)} items.")

    if cost_report:
        n = len(dataset.items)
        print("\n  Cost Report")
        print(f"  {'─' * 40}")
        print(f"  {'Model':<22} {model}")
        print(f"  {'Items':<22} {n}")
        print(f"  {'Prompt tokens':<22} {total_prompt_tokens:,}")
        print(f"  {'Completion tokens':<22} {total_completion_tokens:,}")
        print(f"  {'Total tokens':<22} {total_prompt_tokens + total_completion_tokens:,}")
        print(f"  {'Total cost (USD)':<22} ${total_cost_usd:.4f}")
        print(f"  {'Cost per item (USD)':<22} ${total_cost_usd / max(n, 1):.4f}")
        print(f"  {'─' * 40}\n")
