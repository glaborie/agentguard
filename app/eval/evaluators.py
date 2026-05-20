"""Evaluation functions: code-based checks and LLM-as-judge."""

import json
import re

from langchain_openai import ChatOpenAI

from app.config import settings


# ── Code-based evaluators ──────────────────────────────────────────

def has_source_citation(output: str) -> bool:
    """Check if the response references a source."""
    patterns = [r"\[source:", r"according to", r"based on", r"from the"]
    return any(re.search(p, output, re.IGNORECASE) for p in patterns)


def is_within_length(output: str, max_words: int = 500) -> bool:
    return len(output.split()) <= max_words


def contains_no_hallucination_markers(output: str) -> bool:
    """Flag common hedging that may indicate hallucination."""
    markers = ["i think", "i believe", "probably", "i'm not sure but"]
    text_lower = output.lower()
    return not any(m in text_lower for m in markers)


def is_valid_json(output: str) -> bool:
    try:
        json.loads(output)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


# ── LLM-as-judge evaluator ─────────────────────────────────────────

JUDGE_PROMPT = """\
You are an expert evaluator. Score the following AI assistant response \
on a scale of 0 or 1 (binary: pass/fail) for each criterion.

Question: {question}
Context provided: {context}
Response: {response}

Evaluate:
1. relevance: Does the response answer the question? (0 or 1)
2. faithfulness: Is the response grounded in the provided context? (0 or 1)
3. completeness: Does the response adequately cover the question? (0 or 1)

Respond in JSON only:
{{"relevance": 0 or 1, "faithfulness": 0 or 1, "completeness": 0 or 1, "reasoning": "brief explanation"}}
"""


def llm_as_judge(
    question: str,
    context: str,
    response: str,
    model: str | None = None,
) -> dict:
    llm = ChatOpenAI(
        model=model or settings.default_model,
        base_url=f"{settings.litellm_base_url}/v1",
        api_key=settings.litellm_master_key,
        temperature=0.0,
    )
    prompt = JUDGE_PROMPT.format(
        question=question, context=context, response=response
    )
    result = llm.invoke(prompt)
    try:
        return json.loads(result.content)
    except (json.JSONDecodeError, TypeError):
        return {"relevance": 0, "faithfulness": 0, "completeness": 0, "reasoning": result.content}
