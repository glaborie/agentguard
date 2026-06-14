"""Pure code-based scoring functions — no LLM calls, fully unit-testable."""

from __future__ import annotations

import re
from pathlib import Path

_ESCALATION_PHRASES = [
    "sales team", "account executive", "account manager", "contact us",
    "reach out", "schedule a call", "book a call", "get back to you",
    "escalate", "speak with", "talk to", "connect you with", "follow up",
    "our team will", "someone from our", "i'll have",
]

_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "are", "was", "were", "be", "been", "being", "do",
    "does", "did", "not", "no", "if", "it", "its", "this", "that", "we",
    "you", "your", "our", "can", "will", "would", "should", "may", "might",
    "i", "as", "from", "by", "only", "any", "all",
}


def _posix(p: str) -> str:
    """Normalize OS path separators to forward slashes for cross-platform matching."""
    return p.replace("\\", "/")


def eval_retrieval_hit(retrieved_sources: list[str], gold_docs: list[str]) -> float:
    """1.0 if at least one gold doc appears in the retrieved sources, else 0.0.

    Matching is by filename — a retrieved chunk from
    '02_products/plans-and-pricing.md' matches gold_doc 'plans-and-pricing.md'
    as well as the full path '02_products/plans-and-pricing.md'.

    Paths are normalized to forward slashes before comparison so that
    Windows-style backslash sources (stored by the ingestor on Windows)
    match correctly when evaluated on Linux/WSL.
    """
    if not gold_docs:
        return 1.0  # no expectation → vacuously correct
    retrieved_filenames = {Path(_posix(s)).name for s in retrieved_sources}
    retrieved_paths = {_posix(s) for s in retrieved_sources}
    for gold in gold_docs:
        gold_posix = _posix(gold)
        if Path(gold_posix).name in retrieved_filenames or gold_posix in retrieved_paths:
            return 1.0
    return 0.0


def eval_factual_coverage(answer: str, expected_facts: list[str]) -> float:
    """Fraction of expected facts whose key tokens all appear in the answer.

    A fact is 'covered' if every non-stop-word token from the fact string
    appears (case-insensitive) somewhere in the answer.
    """
    if not expected_facts:
        return 1.0  # no expectation → vacuously correct

    answer_lower = answer.lower()
    covered = 0
    for fact in expected_facts:
        tokens = [
            t.lower()
            for t in re.split(r"\W+", fact)
            if t.lower() not in _STOP_WORDS and len(t) > 2
        ]
        if not tokens:
            covered += 1
            continue

        # Accept a token if it appears as-is OR without a trailing 's'/'es'
        # (handles singular/plural mismatches like "deals" vs "deal").
        def _token_present(t: str) -> bool:
            if t in answer_lower:
                return True
            stem = (
                t[:-2] if t.endswith("es") and len(t) > 4
                else t[:-1] if t.endswith("s") and len(t) > 3
                else t
            )
            return stem in answer_lower

        if all(_token_present(t) for t in tokens):
            covered += 1
    return round(covered / len(expected_facts), 3)


def eval_escalation(answer: str, should_escalate: bool) -> float:
    """1.0 if escalation behaviour matches expectation, else 0.0."""
    answer_lower = answer.lower()
    did_escalate = any(phrase in answer_lower for phrase in _ESCALATION_PHRASES)
    return 1.0 if (did_escalate == should_escalate) else 0.0
