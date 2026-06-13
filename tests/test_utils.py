"""Tests for app.utils — utility functions.

Unit tests for text processing and data extraction utilities.
"""

from unittest.mock import MagicMock

import pytest

from app.utils import extract_trace_output, truncate


class TestTruncate:
    def test_text_within_limit(self):
        """Text within limit is returned unchanged."""
        text = "Hello world"
        result = truncate(text, max_len=20)
        assert result == "Hello world"

    def test_text_at_limit(self):
        """Text at exact limit is returned unchanged."""
        text = "1234567890"
        result = truncate(text, max_len=10)
        assert result == "1234567890"

    def test_text_exceeds_limit(self):
        """Text exceeding limit is truncated with ellipsis."""
        text = "Hello world this is a long message"
        result = truncate(text, max_len=10)
        assert result == "Hello w..."
        assert len(result) == 10

    def test_text_exceeds_limit_edge_case(self):
        """Text just over limit is truncated."""
        text = "12345678901"
        result = truncate(text, max_len=10)
        assert result == "1234567..."
        assert len(result) == 10

    def test_empty_string(self):
        """Empty string returns empty."""
        result = truncate("", max_len=10)
        assert result == ""

    def test_max_len_smaller_than_ellipsis(self):
        """Edge case when max_len is very small."""
        # Even with max_len=3, we compute text[:0] + "..." = "..."
        result = truncate("hello", max_len=3)
        assert result == "..."

    def test_unicode_text(self):
        """Unicode text is truncated correctly."""
        text = "Hello 世界"
        result = truncate(text, max_len=7)
        # len("Hello ") = 6, so we can fit it
        assert len(result) <= 7


class TestExtractTraceOutput:
    def test_none_output(self):
        """None output returns None."""
        trace = MagicMock()
        trace.output = None
        result = extract_trace_output(trace)
        assert result is None

    def test_string_output(self):
        """String output is returned as-is."""
        trace = MagicMock()
        trace.output = "The answer is 42"
        result = extract_trace_output(trace)
        assert result == "The answer is 42"

    def test_dict_output_with_output_key(self):
        """Dict with 'output' key returns its value."""
        trace = MagicMock()
        trace.output = {"output": "The answer"}
        result = extract_trace_output(trace)
        assert result == "The answer"

    def test_dict_output_with_text_key_fallback(self):
        """Dict without 'output' key falls back to 'text'."""
        trace = MagicMock()
        trace.output = {"text": "Text answer"}
        result = extract_trace_output(trace)
        assert result == "Text answer"

    def test_dict_output_no_output_or_text(self):
        """Dict without 'output' or 'text' returns str representation."""
        trace = MagicMock()
        trace.output = {"field": "value", "other": "data"}
        result = extract_trace_output(trace)
        # Should be stringified dict
        assert isinstance(result, str)
        assert "field" in result or "value" in result

    def test_dict_output_empty_string_keys(self):
        """Dict with empty 'output' falls back to 'text'."""
        trace = MagicMock()
        trace.output = {"output": "", "text": "Fallback text"}
        result = extract_trace_output(trace)
        assert result == "Fallback text"

    def test_dict_output_empty_output_none_text(self):
        """Dict with empty 'output' and missing 'text' returns str of dict."""
        trace = MagicMock()
        trace.output = {"output": "", "other": "data"}
        result = extract_trace_output(trace)
        assert isinstance(result, str)

    def test_non_dict_non_string_output(self):
        """Non-dict, non-string output is stringified."""
        trace = MagicMock()
        trace.output = 42
        result = extract_trace_output(trace)
        assert result == "42"

    def test_list_output(self):
        """List output is stringified."""
        trace = MagicMock()
        trace.output = [1, 2, 3]
        result = extract_trace_output(trace)
        assert result == "[1, 2, 3]"

    def test_complex_nested_dict(self):
        """Complex nested dict is handled."""
        trace = MagicMock()
        trace.output = {
            "output": "Main answer",
            "metadata": {"nested": "value"},
        }
        result = extract_trace_output(trace)
        assert result == "Main answer"

    def test_dict_with_falsy_output_truthy_text(self):
        """Dict with falsy 'output' but truthy 'text' returns 'text'."""
        trace = MagicMock()
        trace.output = {"output": None, "text": "Real text"}
        result = extract_trace_output(trace)
        assert result == "Real text"
