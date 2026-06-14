"""LLM-as-judge metrics for policy violation and helpfulness."""

from __future__ import annotations

import json
import re

from langchain_openai import ChatOpenAI

from app.agent.prompts import BENCHMARK_HELPFULNESS_JUDGE_PROMPT, BENCHMARK_POLICY_JUDGE_PROMPT
from app.core.config import settings


def _get_judge_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.deepeval_model,
        base_url=f"{settings.litellm_base_url}/v1",
        api_key=settings.litellm_master_key,
        temperature=0.0,
    )


def _parse_judge_json(content: str) -> dict:
    """Extract and parse a JSON object from an LLM response.

    Handles markdown code fences (```json ... ```) and stray prose around the object.
    """
    content = content.strip()
    if content.startswith("{"):
        return json.loads(content)
    stripped = re.sub(r"^```(?:json)?\s*\n?|\n?```\s*$", "", content).strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    m = re.search(r"\{[^{}]*\}", content, re.DOTALL)
    if m:
        return json.loads(m.group())
    raise ValueError(f"No JSON object found in judge response: {content!r}")


def eval_policy_violation(question: str, answer: str) -> tuple[float, str]:
    """Returns (0.0 or 1.0, reason string)."""
    llm = _get_judge_llm()
    prompt = BENCHMARK_POLICY_JUDGE_PROMPT.format(question=question, response=answer)
    try:
        result = _parse_judge_json(llm.invoke(prompt).content)
        violated = bool(result.get("violation", False))
        return (1.0 if violated else 0.0), result.get("reason", "")
    except Exception as exc:
        return 0.0, f"judge error: {exc}"


def eval_helpfulness(question: str, answer: str) -> tuple[float, str]:
    """Returns (1–5 float, reason string)."""
    llm = _get_judge_llm()
    prompt = BENCHMARK_HELPFULNESS_JUDGE_PROMPT.format(question=question, response=answer)
    try:
        result = _parse_judge_json(llm.invoke(prompt).content)
        score = float(result.get("score", 3))
        return max(1.0, min(5.0, score)), result.get("reason", "")
    except Exception as exc:
        return 3.0, f"judge error: {exc}"
