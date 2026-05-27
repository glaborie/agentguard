"""Tests for code-based evaluators in app.eval.evaluators.

Pure unit tests — no LLM calls, no Docker services.
"""

import pytest

from app.eval.evaluators import (
    contains_no_hallucination_markers,
    has_source_citation,
    is_valid_json,
    is_within_length,
)


class TestHasSourceCitation:
    @pytest.mark.parametrize(
        "text",
        [
            "[Source: 02_products/plans-and-pricing.md] The Starter plan includes...",
            "According to the Langfuse documentation, tracing is...",
            "Based on the provided context, the answer is...",
            "From the academy materials, we can see that...",
        ],
    )
    def test_detects_citations(self, text):
        assert has_source_citation(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "Tracing captures the full execution path.",
            "The AI engineering loop has five phases.",
            "",
        ],
    )
    def test_rejects_no_citation(self, text):
        assert has_source_citation(text) is False


class TestIsWithinLength:
    def test_under_limit(self):
        assert is_within_length("word " * 100) is True

    def test_at_limit(self):
        assert is_within_length("word " * 500) is True

    def test_over_limit(self):
        assert is_within_length("word " * 501) is False

    def test_custom_limit(self):
        assert is_within_length("one two three", max_words=2) is False
        assert is_within_length("one two three", max_words=3) is True

    def test_empty(self):
        assert is_within_length("") is True


class TestContainsNoHallucinationMarkers:
    @pytest.mark.parametrize(
        "text",
        [
            "The five phases are Trace, Monitor, Datasets, Experiment, Evaluate.",
            "Langfuse provides full observability for LLM applications.",
        ],
    )
    def test_clean_output(self, text):
        assert contains_no_hallucination_markers(text) is True

    @pytest.mark.parametrize(
        "marker",
        ["I think", "I believe", "probably", "I'm not sure but"],
    )
    def test_flags_hedging(self, marker):
        text = f"{marker} the answer is tracing."
        assert contains_no_hallucination_markers(text) is False

    def test_case_insensitive(self):
        assert contains_no_hallucination_markers("I THINK it works") is False


class TestIsValidJson:
    def test_valid_object(self):
        assert is_valid_json('{"key": "value"}') is True

    def test_valid_array(self):
        assert is_valid_json('[1, 2, 3]') is True

    def test_invalid(self):
        assert is_valid_json("not json at all") is False

    def test_empty_string(self):
        assert is_valid_json("") is False

    def test_none(self):
        assert is_valid_json(None) is False
