"""Tests for agent tools (app.agent.tools).

Unit tests mock Langfuse client and Qdrant retriever to test tool logic
without requiring the Docker stack.
"""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.agent.tools import (
    _truncate,
    get_dataset_summary,
    get_trace_detail,
    list_traces,
    score_response,
    search_docs,
)


# ── Helper factories ──────────────────────────────────────────────

def _make_trace(trace_id="abc123def456", input_val="What is tracing?", output_val="Tracing is...", latency=1.5, ts=None):
    return SimpleNamespace(
        id=trace_id,
        input=input_val,
        output=output_val,
        latency=latency,
        timestamp=ts or datetime(2026, 5, 20, 14, 30),
    )


def _make_observation(name="ChatOpenAI", obs_type="generation", latency=0.8, model="llama3", usage=None):
    return SimpleNamespace(
        name=name,
        type=obs_type,
        latency=latency,
        model=model,
        usage=usage or SimpleNamespace(input=100, output=50),
    )


def _make_doc(content="Tracing captures execution paths.", source="https://langfuse.com/academy/tracing"):
    return SimpleNamespace(
        page_content=content,
        metadata={"source": source},
    )


# ── search_docs ───────────────────────────────────────────────────

class TestSearchDocs:
    @patch("app.agent.tools.get_retriever")
    def test_returns_formatted_docs(self, mock_retriever):
        mock_ret = MagicMock()
        mock_ret.invoke.return_value = [_make_doc(), _make_doc(content="Monitoring overview.", source="monitoring.md")]
        mock_retriever.return_value = mock_ret

        result = search_docs.invoke({"query": "tracing"})
        assert "Tracing captures" in result
        assert "Monitoring overview" in result
        mock_ret.invoke.assert_called_once_with("tracing")

    @patch("app.agent.tools.get_retriever")
    def test_no_results(self, mock_retriever):
        mock_ret = MagicMock()
        mock_ret.invoke.return_value = []
        mock_retriever.return_value = mock_ret

        result = search_docs.invoke({"query": "nonexistent"})
        assert "No relevant documents" in result


# ── list_traces ───────────────────────────────────────────────────

class TestListTraces:
    @patch("app.agent.tools.get_langfuse_client")
    def test_returns_trace_summary(self, mock_client):
        client = MagicMock()
        client.api.trace.list.return_value = SimpleNamespace(data=[_make_trace()])
        mock_client.return_value = client

        result = list_traces.invoke({"limit": 5})
        assert "abc123def456"[:12] in result
        assert "2026-05-20" in result
        assert "1.5s" in result
        assert "What is tracing?" in result

    @patch("app.agent.tools.get_langfuse_client")
    def test_empty_traces(self, mock_client):
        client = MagicMock()
        client.api.trace.list.return_value = SimpleNamespace(data=[])
        mock_client.return_value = client

        result = list_traces.invoke({"limit": 5})
        assert "No traces found" in result

    @patch("app.agent.tools.get_langfuse_client")
    def test_limit_clamped_to_50(self, mock_client):
        client = MagicMock()
        client.api.trace.list.return_value = SimpleNamespace(data=[])
        mock_client.return_value = client

        list_traces.invoke({"limit": 100})
        client.api.trace.list.assert_called_once_with(limit=50)

    @patch("app.agent.tools.get_langfuse_client")
    def test_limit_clamped_to_1(self, mock_client):
        client = MagicMock()
        client.api.trace.list.return_value = SimpleNamespace(data=[])
        mock_client.return_value = client

        list_traces.invoke({"limit": -5})
        client.api.trace.list.assert_called_once_with(limit=1)

    @patch("app.agent.tools.get_langfuse_client")
    def test_handles_none_fields(self, mock_client):
        client = MagicMock()
        trace = SimpleNamespace(id="x" * 20, input=None, output=None, latency=None, timestamp=None)
        client.api.trace.list.return_value = SimpleNamespace(data=[trace])
        mock_client.return_value = client

        result = list_traces.invoke({"limit": 1})
        assert "n/a" in result


# ── get_trace_detail ──────────────────────────────────────────────

class TestGetTraceDetail:
    @patch("app.agent.tools.get_langfuse_client")
    def test_returns_full_trace(self, mock_client):
        client = MagicMock()
        trace = SimpleNamespace(
            id="abc123",
            name="rag-query",
            timestamp=datetime(2026, 5, 20),
            latency=2.1,
            input="What is tracing?",
            output="Tracing captures...",
            scores=[SimpleNamespace(name="accuracy", value=0.9)],
            observations=[_make_observation()],
        )
        client.api.trace.get.return_value = trace
        mock_client.return_value = client

        result = get_trace_detail.invoke({"trace_id": "abc123"})
        assert "abc123" in result
        assert "rag-query" in result
        assert "2.1s" in result
        assert "accuracy" in result
        assert "0.9" in result
        assert "ChatOpenAI" in result
        assert "llama3" in result
        assert "100 in / 50 out" in result

    @patch("app.agent.tools.get_langfuse_client")
    def test_handles_fetch_error(self, mock_client):
        client = MagicMock()
        client.api.trace.get.side_effect = Exception("not found")
        mock_client.return_value = client

        result = get_trace_detail.invoke({"trace_id": "bad-id"})
        assert "Error fetching trace" in result

    @patch("app.agent.tools.get_langfuse_client")
    def test_no_observations(self, mock_client):
        client = MagicMock()
        trace = SimpleNamespace(
            id="abc", name=None, timestamp=None, latency=None,
            input="q", output="a", scores=[], observations=[],
        )
        client.api.trace.get.return_value = trace
        mock_client.return_value = client

        result = get_trace_detail.invoke({"trace_id": "abc"})
        assert "abc" in result
        assert "Observations" not in result


# ── score_response ────────────────────────────────────────────────

class TestScoreResponse:
    def test_all_pass(self):
        text = "According to the Langfuse docs, tracing is the process of recording."
        result = json.loads(score_response.invoke({"response_text": text}))
        assert result["summary"] == "3/3 checks passed"
        assert result["scores"]["has_source_citation"] is True
        assert result["scores"]["is_within_length"] is True
        assert result["scores"]["no_hallucination_markers"] is True

    def test_no_citation(self):
        text = "Tracing helps with debugging."
        result = json.loads(score_response.invoke({"response_text": text}))
        assert result["scores"]["has_source_citation"] is False

    def test_hallucination_marker(self):
        text = "I think tracing might be useful, based on the docs."
        result = json.loads(score_response.invoke({"response_text": text}))
        assert result["scores"]["no_hallucination_markers"] is False
        assert result["scores"]["has_source_citation"] is True

    def test_over_length(self):
        text = "word " * 600
        result = json.loads(score_response.invoke({"response_text": text}))
        assert result["scores"]["is_within_length"] is False


# ── get_dataset_summary ───────────────────────────────────────────

class TestGetDatasetSummary:
    @patch("app.agent.tools.get_langfuse_client")
    def test_list_datasets(self, mock_client):
        client = MagicMock()
        ds = SimpleNamespace(name="rag-eval-v1", items_count=10)
        client.api.datasets.list.return_value = SimpleNamespace(data=[ds])
        mock_client.return_value = client

        result = get_dataset_summary.invoke({"dataset_name": ""})
        assert "rag-eval-v1" in result
        assert "10" in result

    @patch("app.agent.tools.get_langfuse_client")
    def test_no_datasets(self, mock_client):
        client = MagicMock()
        client.api.datasets.list.return_value = SimpleNamespace(data=[])
        mock_client.return_value = client

        result = get_dataset_summary.invoke({"dataset_name": ""})
        assert "No datasets found" in result

    @patch("app.agent.tools.get_langfuse_client")
    def test_specific_dataset(self, mock_client):
        client = MagicMock()
        items = [
            SimpleNamespace(input={"question": "What is tracing?"}, expected_output="Tracing is..."),
            SimpleNamespace(input={"question": "What is monitoring?"}, expected_output=None),
        ]
        client.get_dataset.return_value = SimpleNamespace(items=items)
        mock_client.return_value = client

        result = get_dataset_summary.invoke({"dataset_name": "my-ds"})
        assert "2 item(s)" in result
        assert "What is tracing?" in result

    @patch("app.agent.tools.get_langfuse_client")
    def test_dataset_not_found(self, mock_client):
        client = MagicMock()
        client.get_dataset.side_effect = Exception("not found")
        mock_client.return_value = client

        result = get_dataset_summary.invoke({"dataset_name": "bad"})
        assert "Error fetching dataset" in result

    @patch("app.agent.tools.get_langfuse_client")
    def test_empty_dataset(self, mock_client):
        client = MagicMock()
        client.get_dataset.return_value = SimpleNamespace(items=[])
        mock_client.return_value = client

        result = get_dataset_summary.invoke({"dataset_name": "empty-ds"})
        assert "no items" in result


# ── _truncate ─────────────────────────────────────────────────────

class TestTruncate:
    def test_short_text_unchanged(self):
        assert _truncate("hello", 10) == "hello"

    def test_long_text_truncated(self):
        result = _truncate("a" * 100, 20)
        assert len(result) == 20
        assert result.endswith("...")

    def test_exact_length_unchanged(self):
        assert _truncate("12345", 5) == "12345"
