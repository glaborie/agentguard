"""RAGAS metric runner wired through the LiteLLM proxy.

Wraps ragas 0.2.x evaluate() API. All judge LLM and embedding calls
go through LiteLLM so they are rate-limited, proxied, and traced.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import settings

if TYPE_CHECKING:
    from ragas import EvaluationDataset  # type: ignore

log = logging.getLogger(__name__)

# Metric names exposed to callers
ALL_METRICS = [
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "answer_correctness",
]


def _build_llm(model: str | None = None) -> "ChatOpenAI":
    return ChatOpenAI(
        model=model or settings.ragas_model or settings.default_model,
        base_url=f"{settings.litellm_base_url}/v1",
        api_key=settings.litellm_master_key,
        temperature=0.0,
        extra_body={"guardrails": []},  # eval prompts contain phrases that trip content guardrails
    )


def _build_embeddings() -> "OpenAIEmbeddings":
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        openai_api_base=f"{settings.litellm_base_url}/v1",
        openai_api_key=settings.litellm_master_key,
    )


def _get_metric_objects(names: list[str], model: str | None = None) -> list:
    from ragas.metrics import (  # type: ignore
        answer_correctness,
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )
    from ragas.llms import LangchainLLMWrapper  # type: ignore
    from ragas.embeddings import LangchainEmbeddingsWrapper  # type: ignore

    llm = LangchainLLMWrapper(_build_llm(model))
    emb = LangchainEmbeddingsWrapper(_build_embeddings())

    registry = {
        "faithfulness":       faithfulness,
        "answer_relevancy":   answer_relevancy,
        "context_precision":  context_precision,
        "context_recall":     context_recall,
        "answer_correctness": answer_correctness,
    }

    selected = [registry[n] for n in names if n in registry]

    for m in selected:
        m.llm = llm
        if hasattr(m, "embeddings"):
            m.embeddings = emb

    return selected


def build_ragas_dataset(
    questions: list[str],
    generated_answers: list[str],
    retrieved_contexts: list[list[str]],
    ground_truths: list[str] | None = None,
) -> "EvaluationDataset":
    """Assemble a RAGAS EvaluationDataset from parallel lists."""
    from ragas import EvaluationDataset, SingleTurnSample  # type: ignore

    samples = []
    for i, (q, ans, ctx) in enumerate(zip(questions, generated_answers, retrieved_contexts)):
        ref = ground_truths[i] if ground_truths else None
        samples.append(
            SingleTurnSample(
                user_input=q,
                response=ans,
                retrieved_contexts=ctx,
                reference=ref,
            )
        )
    return EvaluationDataset(samples=samples)


def run_ragas_evaluation(
    dataset: "EvaluationDataset",
    metric_names: list[str] | None = None,
    model: str | None = None,
) -> list[dict[str, float]]:
    """Run RAGAS metrics and return per-sample score dicts.

    Returns a list of {metric_name: score} dicts, one per sample.
    """
    from ragas import evaluate  # type: ignore

    names   = metric_names or ALL_METRICS
    metrics = _get_metric_objects(names, model)

    log.info("Running RAGAS metrics: %s", names)
    result = asyncio.run(evaluate(dataset=dataset, metrics=metrics))

    # result.scores is a list[dict] or a pandas-compatible object
    try:
        scores_list: list[dict] = result.scores.to_list() if hasattr(result.scores, "to_list") else list(result.scores)
    except Exception:
        # fallback: convert Dataset to list of dicts
        scores_list = [dict(zip(result.scores.column_names, row)) for row in zip(*result.scores.to_list())]  # type: ignore

    return scores_list
