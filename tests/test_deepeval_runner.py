"""Tests for app.eval.deepeval_runner — DeepEval metric execution and Langfuse integration.

Unit tests with mocked LLM calls and Langfuse operations.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from app.eval.deepeval_runner import run_deepeval_evaluation


@pytest.fixture
def mock_langfuse_client():
    """Mock Langfuse client with dataset and score methods."""
    client = MagicMock()
    
    # Mock dataset with items
    item1 = Mock()
    item1.input = {"question": "What is tracing?"}
    item1.expected_output = "Tracing captures execution flow."
    
    item2 = Mock()
    item2.input = {"question": "What is observability?"}
    item2.expected_output = "Observability measures system state."
    
    dataset = Mock()
    dataset.items = [item1, item2]
    client.get_dataset.return_value = dataset
    
    # Mock score creation
    client.create_score = MagicMock()
    client.flush = MagicMock()
    
    return client


@pytest.fixture
def mock_metrics():
    """Mock DeepEval metric classes."""
    metric1 = MagicMock()
    metric1.__class__.__name__ = "Faithfulness"
    metric1.score = 0.85
    metric1.reason = "Good faithfulness"
    metric1.measure = MagicMock()
    
    metric2 = MagicMock()
    metric2.__class__.__name__ = "AnswerRelevancy"
    metric2.score = 0.92
    metric2.reason = "Highly relevant"
    metric2.measure = MagicMock()
    
    return [metric1, metric2]


@pytest.fixture
def mock_retriever():
    """Mock RAG retriever."""
    retriever = MagicMock()
    
    doc1 = MagicMock()
    doc1.page_content = "Tracing is a technique for capturing execution flow."
    doc2 = MagicMock()
    doc2.page_content = "It helps identify performance bottlenecks."
    
    retriever.invoke.return_value = [doc1, doc2]
    return retriever


class TestRunDeepevalEvaluation:
    @patch("app.eval.deepeval_runner.get_langfuse_handler")
    @patch("app.eval.deepeval_runner.query_with_usage")
    @patch("app.eval.deepeval_runner.get_retriever")
    @patch("app.eval.deepeval_runner.get_metrics")
    @patch("app.eval.deepeval_runner.get_langfuse_client")
    def test_evaluates_dataset_with_all_metrics(
        self,
        mock_get_client,
        mock_get_metrics,
        mock_get_retriever,
        mock_query_with_usage,
        mock_get_handler,
        mock_langfuse_client,
        mock_metrics,
        mock_retriever,
        capsys,
    ):
        """Test evaluation of full dataset with all metrics."""
        mock_get_client.return_value = mock_langfuse_client
        mock_get_metrics.return_value = mock_metrics
        mock_get_retriever.return_value = mock_retriever
        mock_query_with_usage.return_value = (
            "Tracing captures execution flow.",
            {"prompt_tokens": 10, "completion_tokens": 20, "cost_usd": 0.01},
        )
        handler = MagicMock()
        handler.trace_id = "trace-123"
        mock_get_handler.return_value = handler

        run_deepeval_evaluation(dataset_name="test-dataset")

        # Verify dataset was fetched
        mock_get_client.assert_called_once()
        mock_langfuse_client.get_dataset.assert_called_once_with("test-dataset")

        # Verify metrics retrieved without filter
        mock_get_metrics.assert_called_once()
        call_kwargs = mock_get_metrics.call_args[1]
        assert call_kwargs["names"] is None

        # Verify retriever initialized
        mock_get_retriever.assert_called_once_with(k=6)

        # Verify query called for each item
        assert mock_query_with_usage.call_count == 2

        # Verify scores created for each item x metric
        assert mock_langfuse_client.create_score.call_count == 4  # 2 items x 2 metrics

        # Verify client flushed
        mock_langfuse_client.flush.assert_called_once()

        # Verify output
        output = capsys.readouterr().out
        assert "test-dataset" in output
        assert "Done. Scores pushed to Langfuse for 2 items." in output

    @patch("app.eval.deepeval_runner.get_langfuse_handler")
    @patch("app.eval.deepeval_runner.query_with_usage")
    @patch("app.eval.deepeval_runner.get_retriever")
    @patch("app.eval.deepeval_runner.get_metrics")
    @patch("app.eval.deepeval_runner.get_langfuse_client")
    def test_filters_metrics_by_name(
        self,
        mock_get_client,
        mock_get_metrics,
        mock_get_retriever,
        mock_query_with_usage,
        mock_get_handler,
        mock_langfuse_client,
        mock_metrics,
        mock_retriever,
    ):
        """Test that metric_names filter is passed through."""
        mock_get_client.return_value = mock_langfuse_client
        mock_get_metrics.return_value = [mock_metrics[0]]  # Only first metric
        mock_get_retriever.return_value = mock_retriever
        mock_query_with_usage.return_value = ("output", {"prompt_tokens": 5, "completion_tokens": 10, "cost_usd": 0.005})
        mock_get_handler.return_value = MagicMock(trace_id="trace-123")

        run_deepeval_evaluation(
            dataset_name="test-dataset",
            metric_names=["Faithfulness"],
        )

        # Verify metric filter was passed
        call_kwargs = mock_get_metrics.call_args[1]
        assert call_kwargs["names"] == ["Faithfulness"]

        # Should only create scores for 1 metric x 2 items
        assert mock_langfuse_client.create_score.call_count == 2

    @patch("app.eval.deepeval_runner.get_langfuse_handler")
    @patch("app.eval.deepeval_runner.query_with_usage")
    @patch("app.eval.deepeval_runner.get_retriever")
    @patch("app.eval.deepeval_runner.get_metrics")
    @patch("app.eval.deepeval_runner.get_langfuse_client")
    def test_no_metrics_exits_gracefully(
        self,
        mock_get_client,
        mock_get_metrics,
        mock_get_retriever,
        mock_query_with_usage,
        mock_get_handler,
        mock_langfuse_client,
        mock_retriever,
        capsys,
    ):
        """Test early exit if no metrics available."""
        mock_get_client.return_value = mock_langfuse_client
        mock_get_metrics.return_value = []  # No metrics

        run_deepeval_evaluation(dataset_name="test-dataset")

        # Should not call retriever or query
        mock_get_retriever.assert_not_called()
        mock_query_with_usage.assert_not_called()

        output = capsys.readouterr().out
        assert "No valid metrics selected." in output

    @patch("app.eval.deepeval_runner.get_langfuse_handler")
    @patch("app.eval.deepeval_runner.query_with_usage")
    @patch("app.eval.deepeval_runner.get_retriever")
    @patch("app.eval.deepeval_runner.get_metrics")
    @patch("app.eval.deepeval_runner.get_langfuse_client")
    def test_cost_report_printed(
        self,
        mock_get_client,
        mock_get_metrics,
        mock_get_retriever,
        mock_query_with_usage,
        mock_get_handler,
        mock_langfuse_client,
        mock_metrics,
        mock_retriever,
        capsys,
    ):
        """Test cost report is printed when requested."""
        mock_get_client.return_value = mock_langfuse_client
        mock_get_metrics.return_value = [mock_metrics[0]]
        mock_get_retriever.return_value = mock_retriever
        mock_query_with_usage.return_value = (
            "output",
            {"prompt_tokens": 100, "completion_tokens": 50, "cost_usd": 0.10},
        )
        mock_get_handler.return_value = MagicMock(trace_id="trace-123")

        run_deepeval_evaluation(
            dataset_name="test-dataset",
            cost_report=True,
        )

        output = capsys.readouterr().out
        assert "Cost Report" in output
        assert "Prompt tokens" in output
        assert "200" in output  # 2 items × 100 prompt tokens
        assert "Completion tokens" in output
        assert "$0.20" in output  # 2 items × 0.10 cost

    @patch("app.eval.deepeval_runner.get_langfuse_handler")
    @patch("app.eval.deepeval_runner.query_with_usage")
    @patch("app.eval.deepeval_runner.get_retriever")
    @patch("app.eval.deepeval_runner.get_metrics")
    @patch("app.eval.deepeval_runner.get_langfuse_client")
    def test_metric_measure_error_caught(
        self,
        mock_get_client,
        mock_get_metrics,
        mock_get_retriever,
        mock_query_with_usage,
        mock_get_handler,
        mock_langfuse_client,
        mock_retriever,
        capsys,
    ):
        """Test that metric measure errors are caught and logged."""
        mock_get_client.return_value = mock_langfuse_client
        
        # Metric that raises on measure
        failing_metric = MagicMock()
        failing_metric.__class__.__name__ = "FailingMetric"
        failing_metric.measure.side_effect = RuntimeError("LLM timeout")
        
        mock_get_metrics.return_value = [failing_metric]
        mock_get_retriever.return_value = mock_retriever
        mock_query_with_usage.return_value = ("output", {"prompt_tokens": 5, "completion_tokens": 10, "cost_usd": 0.005})
        mock_get_handler.return_value = MagicMock(trace_id="trace-123")

        run_deepeval_evaluation(dataset_name="test-dataset")

        output = capsys.readouterr().out
        assert "ERROR" in output
        assert "LLM timeout" in output

    @patch("app.eval.deepeval_runner.get_langfuse_handler")
    @patch("app.eval.deepeval_runner.query_with_usage")
    @patch("app.eval.deepeval_runner.get_retriever")
    @patch("app.eval.deepeval_runner.get_metrics")
    @patch("app.eval.deepeval_runner.get_langfuse_client")
    @patch("app.config.settings")
    def test_model_override(
        self,
        mock_settings,
        mock_get_client,
        mock_get_metrics,
        mock_get_retriever,
        mock_query_with_usage,
        mock_get_handler,
        mock_langfuse_client,
        mock_metrics,
        mock_retriever,
    ):
        """Test that model parameter overrides default."""
        mock_settings.deepeval_model = "default-deepeval-model"
        mock_settings.default_model = "default-model"
        
        mock_get_client.return_value = mock_langfuse_client
        mock_get_metrics.return_value = [mock_metrics[0]]
        mock_get_retriever.return_value = mock_retriever
        mock_query_with_usage.return_value = ("output", {"prompt_tokens": 5, "completion_tokens": 10, "cost_usd": 0.005})
        mock_get_handler.return_value = MagicMock(trace_id="trace-123")

        run_deepeval_evaluation(
            dataset_name="test-dataset",
            model="custom-model",
        )

        # Verify custom model was used for metrics
        call_kwargs = mock_get_metrics.call_args[1]
        assert call_kwargs["model"] == "custom-model"

        # Verify custom model was used for query
        call_kwargs = mock_query_with_usage.call_args[1]
        assert call_kwargs["model"] == "custom-model"
