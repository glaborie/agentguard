"""DeepEval evaluation runner that bridges DeepEval metrics with Langfuse."""

from deepeval.test_case import LLMTestCase

from app.eval.deepeval_metrics import get_metrics
from app.rag.chain import get_retriever, format_docs, query
from app.tracing import get_langfuse_client, get_langfuse_handler


def run_deepeval_evaluation(
    dataset_name: str,
    metric_names: list[str] | None = None,
    model: str | None = None,
) -> None:
    """Run DeepEval metrics against a Langfuse dataset and push scores back.

    Args:
        dataset_name: Name of the Langfuse dataset.
        metric_names: Which metrics to run (None = all).
        model: Override model for both generation and judge.
    """
    from app.config import settings

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

    for i, item in enumerate(dataset.items):
        question = item.input.get("question", str(item.input)) if isinstance(item.input, dict) else str(item.input)
        expected = str(item.expected_output) if item.expected_output else None

        print(f"[{i+1}/{len(dataset.items)}] {question[:80]}...")

        handler = get_langfuse_handler()
        output = query(question=question, model=model, callbacks=[handler])

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
