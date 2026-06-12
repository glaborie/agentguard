"""Unit tests for app.eval.ragas_metrics and RAGAS path in run_ragas_experiment.

Pure unit tests — no LLM calls, no Docker services.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.eval.experiments import ItemResult, run_ragas_experiment
from app.eval.ragas_metrics import ALL_METRICS, build_ragas_dataset


# ── build_ragas_dataset ───────────────────────────────────────────────────────

class TestBuildRagasDataset:
    def test_returns_evaluation_dataset(self):
        from ragas import EvaluationDataset

        ds = build_ragas_dataset(
            questions=["What is watsonx?"],
            generated_answers=["IBM watsonx is an AI platform."],
            retrieved_contexts=[["Context A", "Context B"]],
            ground_truths=["IBM watsonx is an enterprise AI and data platform."],
        )
        assert isinstance(ds, EvaluationDataset)
        assert len(ds.samples) == 1

    def test_sample_fields(self):
        ds = build_ragas_dataset(
            questions=["q1", "q2"],
            generated_answers=["a1", "a2"],
            retrieved_contexts=[["c1"], ["c2", "c3"]],
            ground_truths=["g1", "g2"],
        )
        s0 = ds.samples[0]
        assert s0.user_input == "q1"
        assert s0.response == "a1"
        assert s0.retrieved_contexts == ["c1"]
        assert s0.reference == "g1"

    def test_no_ground_truths(self):
        ds = build_ragas_dataset(
            questions=["q"],
            generated_answers=["a"],
            retrieved_contexts=[["c"]],
            ground_truths=None,
        )
        assert ds.samples[0].reference is None

    def test_multiple_samples(self):
        n = 10
        ds = build_ragas_dataset(
            questions=[f"q{i}" for i in range(n)],
            generated_answers=[f"a{i}" for i in range(n)],
            retrieved_contexts=[[f"c{i}"] for i in range(n)],
        )
        assert len(ds.samples) == n


# ── score normalisation ───────────────────────────────────────────────────────

class TestScoreNormalisation:
    """run_ragas_evaluation handles both Result object and plain dict return."""

    def _mock_evaluate(self, return_value):
        return patch("ragas.evaluate", return_value=return_value)

    def _mock_metrics(self):
        return patch("app.eval.ragas_metrics._get_metric_objects", return_value=[])

    def test_dict_result_broadcasts_to_all_samples(self):
        from app.eval.ragas_metrics import run_ragas_evaluation

        avg_dict = {"faithfulness": 0.8, "answer_relevancy": 0.7}
        ds = build_ragas_dataset(["q1", "q2"], ["a1", "a2"], [["c"], ["c"]])
        with self._mock_metrics(), self._mock_evaluate(avg_dict):
            scores = run_ragas_evaluation(ds, metric_names=["faithfulness"])
        assert len(scores) == 2
        assert scores[0] == avg_dict
        assert scores[1] == avg_dict

    def test_result_object_with_scores_attribute(self):
        from app.eval.ragas_metrics import run_ragas_evaluation

        per_sample = [
            {"faithfulness": 0.9},
            {"faithfulness": 0.6},
        ]
        result_obj = MagicMock()
        result_obj.scores = MagicMock()
        result_obj.scores.to_list.return_value = per_sample

        ds = build_ragas_dataset(["q1", "q2"], ["a1", "a2"], [["c"], ["c"]])
        with self._mock_metrics(), self._mock_evaluate(result_obj):
            scores = run_ragas_evaluation(ds, metric_names=["faithfulness"])
        assert scores == per_sample


# ── ALL_METRICS ───────────────────────────────────────────────────────────────

class TestAllMetrics:
    def test_contains_expected_metrics(self):
        assert "faithfulness" in ALL_METRICS
        assert "answer_relevancy" in ALL_METRICS
        assert "context_precision" in ALL_METRICS
        assert "context_recall" in ALL_METRICS
        assert "answer_correctness" in ALL_METRICS

    def test_metric_count(self):
        assert len(ALL_METRICS) == 5


# ── run_ragas_experiment (mocked) ─────────────────────────────────────────────

class TestRunRagasExperiment:
    def _make_langfuse_item(self, question: str, answer: str):
        item = MagicMock()
        item.input = {"question": question}
        item.expected_output = answer
        item.id = f"item-{question[:4]}"
        return item

    @patch("app.eval.experiments.get_langfuse_client")
    @patch("app.eval.experiments.get_langfuse_handler")
    @patch("app.eval.experiments.get_retriever")
    @patch("app.eval.experiments.query_with_usage")
    @patch("app.eval.ragas_metrics.run_ragas_evaluation")
    @patch("app.eval.ragas_metrics.build_ragas_dataset")
    def test_returns_results_and_run_names(
        self,
        mock_build_ds,
        mock_run_eval,
        mock_query,
        mock_retriever,
        mock_handler_factory,
        mock_client_factory,
    ):
        mock_query.return_value = ("answer", {
            "prompt_tokens": 10, "completion_tokens": 5,
            "total_tokens": 15, "cost_usd": 0.001,
        })
        mock_retriever.return_value.invoke.return_value = []
        mock_handler = MagicMock()
        mock_handler.last_trace_id = "trace-1"
        mock_handler_factory.return_value = mock_handler

        item = self._make_langfuse_item("What is watsonx?", "An AI platform.")
        mock_ds = MagicMock()
        mock_ds.items = [item]
        mock_client = MagicMock()
        mock_client.get_dataset.return_value = mock_ds
        mock_client_factory.return_value = mock_client

        mock_build_ds.return_value = MagicMock()
        mock_run_eval.return_value = [{"faithfulness": 0.85}]

        results, run_names = run_ragas_experiment(
            dataset_name="watsonx-qa",
            models=["openrouter-gemini-flash"],
            metric_names=["faithfulness"],
            limit=1,
        )

        assert len(results) == 1
        assert results[0].model == "openrouter-gemini-flash"
        assert results[0].scores == {"faithfulness": 0.85}
        assert "openrouter-gemini-flash" in run_names

    @patch("app.eval.experiments.get_langfuse_client")
    @patch("app.eval.experiments.get_langfuse_handler")
    @patch("app.eval.experiments.get_retriever")
    @patch("app.eval.experiments.query_with_usage")
    @patch("app.eval.ragas_metrics.run_ragas_evaluation")
    @patch("app.eval.ragas_metrics.build_ragas_dataset")
    def test_none_scores_skipped(
        self,
        mock_build_ds,
        mock_run_eval,
        mock_query,
        mock_retriever,
        mock_handler_factory,
        mock_client_factory,
    ):
        mock_query.return_value = ("answer", {
            "prompt_tokens": 10, "completion_tokens": 5,
            "total_tokens": 15, "cost_usd": 0.001,
        })
        mock_retriever.return_value.invoke.return_value = []
        mock_handler = MagicMock()
        mock_handler.last_trace_id = "trace-1"
        mock_handler_factory.return_value = mock_handler

        item = self._make_langfuse_item("q", "a")
        mock_ds = MagicMock()
        mock_ds.items = [item]
        mock_client = MagicMock()
        mock_client.get_dataset.return_value = mock_ds
        mock_client_factory.return_value = mock_client

        mock_build_ds.return_value = MagicMock()
        mock_run_eval.return_value = [{"faithfulness": None, "answer_relevancy": 0.7}]

        results, _ = run_ragas_experiment(
            dataset_name="watsonx-qa",
            models=["openrouter-gemini-flash"],
            limit=1,
        )

        assert results[0].scores.get("faithfulness") is None
        assert results[0].scores.get("answer_relevancy") == 0.7
