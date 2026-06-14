"""Benchmark orchestrator — runs items × modes and collects results."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.eval.benchmark.items import BenchmarkItem, BenchmarkResult, RunMode
from app.eval.benchmark.judges import eval_helpfulness, eval_policy_violation
from app.eval.benchmark.metrics import eval_escalation, eval_factual_coverage, eval_retrieval_hit

logger = logging.getLogger(__name__)


def _run_rag(
    question: str,
    guardrails_enabled: bool = True,
    model: str | None = None,
) -> tuple[str, list[str]]:
    """Run the RAG chain and return (answer, retrieved_sources)."""
    from app.rag.chain import build_rag_chain, get_retriever

    retriever = get_retriever(k=6)
    docs = retriever.invoke(question)
    sources = [d.metadata.get("source", "") for d in docs]

    chain = build_rag_chain(model=model, guardrails_enabled=guardrails_enabled)
    answer = chain.invoke(question)
    return answer, sources


def _run_direct(question: str, model: str | None = None) -> tuple[str, list[str]]:
    """Call the LLM directly without retrieval context (baseline)."""
    import httpx

    resp = httpx.post(
        f"{settings.litellm_base_url}/v1/chat/completions",
        json={
            "model": model or settings.default_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful sales assistant for NorthstarCRM.",
                },
                {"role": "user", "content": question},
            ],
        },
        headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        timeout=settings.http_timeout_seconds,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"], []


def run_benchmark(
    items: dict[str, BenchmarkItem],
    retrieval_labels: dict[str, list[str]],
    modes: list[RunMode],
    model: str | None = None,
    llm_judge: bool = True,
    limit: int | None = None,
    verbose: bool = False,
) -> list[BenchmarkResult]:
    """Run the benchmark for each item × mode combination.

    Args:
        items:            benchmark items keyed by id
        retrieval_labels: gold retrieval docs keyed by id
        modes:            which run modes to evaluate
        model:            LLM model override
        llm_judge:        run policy + helpfulness LLM judges (slower)
        limit:            cap number of items (for smoke tests)
        verbose:          log per-question progress
    """
    results: list[BenchmarkResult] = []
    items_list = list(items.values())
    if limit:
        items_list = items_list[:limit]

    for item in items_list:
        gold_docs = retrieval_labels.get(item.id, item.gold_docs)

        for mode in modes:
            if verbose:
                logger.info("  [%s] %s: %s...", mode, item.id, item.question[:60])

            result = BenchmarkResult(
                id=item.id,
                question=item.question,
                answer="",
                mode=mode,
            )

            try:
                if mode == "full":
                    answer, sources = _run_rag(question=item.question, guardrails_enabled=True, model=model)
                elif mode == "no-guardrails":
                    answer, sources = _run_rag(question=item.question, guardrails_enabled=False, model=model)
                else:  # direct
                    answer, sources = _run_direct(question=item.question, model=model)

                result.answer = answer
                result.retrieved_sources = sources
                result.retrieval_hit = eval_retrieval_hit(sources, gold_docs)
                result.factual_coverage = eval_factual_coverage(answer, item.expected_facts)
                result.correct_escalation = eval_escalation(answer, item.should_escalate)

                if llm_judge:
                    result.policy_violation, result.policy_reason = eval_policy_violation(item.question, answer)
                    result.helpfulness, result.helpfulness_reason = eval_helpfulness(item.question, answer)

            except Exception as exc:
                result.error = str(exc)
                if verbose:
                    logger.warning("    ERROR: %s", exc)

            results.append(result)

    return results
