"""Evaluation functions: code-based checks."""

import json
import re


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

