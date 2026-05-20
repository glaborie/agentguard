"""Experiment runner: compare model/prompt variants against a dataset."""

from dataclasses import dataclass, field

from app.eval.evaluators import (
    contains_no_hallucination_markers,
    has_source_citation,
    is_within_length,
    llm_as_judge,
)
from app.rag.chain import query
from app.tracing import get_langfuse_client, get_langfuse_handler


@dataclass
class ExperimentResult:
    question: str
    expected: str | None
    output: str
    model: str
    scores: dict = field(default_factory=dict)


def run_experiment(
    dataset_name: str,
    models: list[str],
    experiment_name: str | None = None,
) -> list[ExperimentResult]:
    """Run all models against a Langfuse dataset and score results."""
    client = get_langfuse_client()
    dataset = client.get_dataset(dataset_name)

    results = []
    for item in dataset.items:
        question = item.input.get("question", str(item.input))
        expected = item.expected_output

        for model_name in models:
            handler = get_langfuse_handler()
            output = query(question=question, model=model_name, callbacks=[handler])

            scores = {
                "has_citation": has_source_citation(output),
                "within_length": is_within_length(output),
                "no_hallucination_markers": contains_no_hallucination_markers(output),
            }

            result = ExperimentResult(
                question=question,
                expected=str(expected) if expected else None,
                output=output,
                model=model_name,
                scores=scores,
            )
            results.append(result)

    client.flush()

    return results


def print_results(results: list[ExperimentResult]):
    for r in results:
        print(f"\n{'='*60}")
        print(f"Model:    {r.model}")
        print(f"Question: {r.question[:80]}")
        print(f"Output:   {r.output[:200]}...")
        print(f"Scores:   {r.scores}")
