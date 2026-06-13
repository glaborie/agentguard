"""Tests for app.eval.service — delegation and service orchestration.

Unit tests with mocked underlying functions.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.eval.service import (
    evaluate,
    experiment,
    ragas_experiment,
    regression_gate,
    show_experiment_table,
)


class TestEvaluate:
    @patch("app.eval.service.run_deepeval_evaluation")
    def test_calls_deepeval_with_defaults(self, mock_run):
        evaluate(dataset_name="test-dataset")

        mock_run.assert_called_once_with(
            dataset_name="test-dataset",
            metric_names=None,
            model=None,
            cost_report=False,
        )

    @patch("app.eval.service.run_deepeval_evaluation")
    def test_calls_deepeval_with_metrics(self, mock_run):
        evaluate(
            dataset_name="test-dataset",
            metric_names=["faithfulness", "relevancy"],
            model="gpt-4",
            cost_report=True,
        )

        mock_run.assert_called_once_with(
            dataset_name="test-dataset",
            metric_names=["faithfulness", "relevancy"],
            model="gpt-4",
            cost_report=True,
        )


class TestExperiment:
    @patch("app.eval.service.run_experiment")
    def test_calls_experiment_with_defaults(self, mock_run):
        mock_run.return_value = ({}, {})
        result = experiment(
            dataset_name="test-dataset",
            models=["model1", "model2"],
        )

        mock_run.assert_called_once_with(
            dataset_name="test-dataset",
            models=["model1", "model2"],
            run_prefix="experiment",
            metric_names=None,
            judge_model=None,
            limit=None,
        )
        assert result == ({}, {})

    @patch("app.eval.service.run_experiment")
    def test_calls_experiment_with_all_args(self, mock_run):
        mock_run.return_value = ({"results": "data"}, {"mapping": "info"})
        result = experiment(
            dataset_name="test-dataset",
            models=["model1"],
            run_prefix="custom-run",
            metric_names=["faithfulness"],
            judge_model="judge-model",
            limit=10,
        )

        mock_run.assert_called_once_with(
            dataset_name="test-dataset",
            models=["model1"],
            run_prefix="custom-run",
            metric_names=["faithfulness"],
            judge_model="judge-model",
            limit=10,
        )
        assert result == ({"results": "data"}, {"mapping": "info"})


class TestShowExperimentTable:
    @patch("app.eval.service.print_comparison_table")
    def test_delegates_to_print_comparison_table(self, mock_print):
        results = {"model1": [0.8, 0.9], "model2": [0.7, 0.85]}
        run_names = {"model1": "Run1", "model2": "Run2"}
        dataset_name = "test-dataset"

        show_experiment_table(results, run_names, dataset_name)

        mock_print.assert_called_once_with(results, run_names, dataset_name)


class TestRagasExperiment:
    @patch("app.eval.service.run_ragas_experiment")
    def test_calls_ragas_with_defaults(self, mock_run):
        mock_run.return_value = ({}, {})
        result = ragas_experiment(
            dataset_name="test-dataset",
            models=["model1"],
        )

        mock_run.assert_called_once_with(
            dataset_name="test-dataset",
            models=["model1"],
            run_prefix="ragas-experiment",
            metric_names=None,
            judge_model=None,
            limit=None,
        )
        assert result == ({}, {})

    @patch("app.eval.service.run_ragas_experiment")
    def test_calls_ragas_with_custom_args(self, mock_run):
        mock_run.return_value = ({"ragas": "results"}, {"mapping": "data"})
        result = ragas_experiment(
            dataset_name="watsonx-qa",
            models=["model1", "model2"],
            run_prefix="ragas-custom",
            metric_names=["faithfulness", "answer_relevancy"],
            judge_model="claude",
            limit=20,
        )

        mock_run.assert_called_once_with(
            dataset_name="watsonx-qa",
            models=["model1", "model2"],
            run_prefix="ragas-custom",
            metric_names=["faithfulness", "answer_relevancy"],
            judge_model="claude",
            limit=20,
        )
        assert result == ({"ragas": "results"}, {"mapping": "data"})


class TestRegressionGate:
    @patch("scripts.regression_gate.run_gate")
    def test_calls_gate_with_defaults(self, mock_gate):
        mock_gate.return_value = True
        result = regression_gate()

        mock_gate.assert_called_once_with(
            dataset_name="rag-golden-set",
            model=None,
            metric_names=None,
            thresholds=None,
            limit=None,
            judge_model=None,
            run_prefix="regression-gate",
            push_scores=True,
        )
        assert result is True

    @patch("scripts.regression_gate.run_gate")
    def test_calls_gate_with_custom_args(self, mock_gate):
        mock_gate.return_value = False
        result = regression_gate(
            dataset_name="custom-dataset",
            model="gpt-4",
            metric_names=["faithfulness"],
            thresholds={"faithfulness": 0.8},
            limit=50,
            judge_model="claude",
            run_prefix="custom-gate",
            push_scores=False,
        )

        mock_gate.assert_called_once_with(
            dataset_name="custom-dataset",
            model="gpt-4",
            metric_names=["faithfulness"],
            thresholds={"faithfulness": 0.8},
            limit=50,
            judge_model="claude",
            run_prefix="custom-gate",
            push_scores=False,
        )
        assert result is False

    @patch("scripts.regression_gate.run_gate")
    def test_gate_failure_propagates(self, mock_gate):
        mock_gate.side_effect = ValueError("Invalid threshold")
        with pytest.raises(ValueError, match="Invalid threshold"):
            regression_gate()
