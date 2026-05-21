"""Seed the rag-eval-v1 dataset in Langfuse for DeepEval evaluation."""

from app.tracing import get_langfuse_client

DATASET_NAME = "rag-eval-v1"

ITEMS = [
    {
        "input": {"question": "What is tracing in Langfuse and why is it useful?"},
        "expected_output": (
            "Tracing in Langfuse captures the full execution path of an LLM application, "
            "recording each step (LLM calls, tool calls, retrieval) as observations nested "
            "under a trace. It is useful for debugging, latency analysis, and understanding "
            "model behaviour in production."
        ),
    },
    {
        "input": {"question": "How do you create a dataset in Langfuse?"},
        "expected_output": (
            "You create a dataset via the Langfuse SDK with `langfuse.create_dataset(name=...)`. "
            "Items are added with `dataset.create_item(input=..., expected_output=...)`. "
            "Datasets are used to run experiments and evaluate model outputs offline."
        ),
    },
    {
        "input": {"question": "What is a Langfuse score and how do you add one to a trace?"},
        "expected_output": (
            "A score is a numeric or categorical value attached to a trace or observation to "
            "capture quality signals. You add one with `langfuse.create_score(trace_id=..., "
            "name=..., value=...)`. Scores power dashboards and experiment comparisons."
        ),
    },
    {
        "input": {"question": "What is the difference between a span and a generation in Langfuse?"},
        "expected_output": (
            "A generation is a specific observation type for LLM calls — it records the model, "
            "prompt tokens, completion tokens, and cost. A span is a generic observation for any "
            "timed step (e.g. a retrieval or tool call) that does not have token-level metadata."
        ),
    },
    {
        "input": {"question": "How does Langfuse support prompt management?"},
        "expected_output": (
            "Langfuse provides a prompt registry where you version and deploy prompts. "
            "Prompts are fetched at runtime with `langfuse.get_prompt(name=..., version=...)` "
            "and linked to traces automatically, so you can correlate prompt versions with "
            "quality scores."
        ),
    },
]


def main():
    client = get_langfuse_client()

    # create_dataset is idempotent — safe to call even if it already exists
    client.create_dataset(
        name=DATASET_NAME,
        description="RAG evaluation questions for Langfuse documentation QA",
    )
    print(f"Dataset '{DATASET_NAME}' ready.")

    for item in ITEMS:
        client.create_dataset_item(
            dataset_name=DATASET_NAME,
            input=item["input"],
            expected_output=item["expected_output"],
        )
    print(f"Seeded {len(ITEMS)} items.")
    client.flush()
    print("Done.")


if __name__ == "__main__":
    main()
