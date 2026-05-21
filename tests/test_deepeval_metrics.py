"""Tests for DeepEval metric configuration (app.eval.deepeval_metrics).

Unit tests validate the LiteLLM model wrapper and metric factory functions
without calling any LLMs.
"""

from unittest.mock import patch

from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
    HallucinationMetric,
)

from app.eval.deepeval_metrics import (
    METRIC_REGISTRY,
    LiteLLMModel,
    get_answer_relevancy_metric,
    get_contextual_relevancy_metric,
    get_faithfulness_metric,
    get_hallucination_metric,
    get_metrics,
)


class TestLiteLLMModel:
    @patch("app.eval.deepeval_metrics.settings")
    def test_default_model_name(self, mock_settings):
        mock_settings.deepeval_model = ""
        mock_settings.default_model = "llama3"
        mock_settings.litellm_base_url = "http://localhost:4000"
        model = LiteLLMModel()
        assert model.get_model_name() == "llama3"

    def test_custom_model_name(self):
        model = LiteLLMModel("mistral")
        assert model.get_model_name() == "mistral"

    @patch("app.eval.deepeval_metrics.settings")
    def test_uses_deepeval_model_setting(self, mock_settings):
        mock_settings.deepeval_model = "openrouter-llama3"
        mock_settings.default_model = "llama3"
        mock_settings.litellm_base_url = "http://localhost:4000"
        mock_settings.litellm_master_key = "sk-test"
        model = LiteLLMModel()
        assert model.get_model_name() == "openrouter-llama3"

    def test_load_model_returns_llm(self):
        model = LiteLLMModel()
        llm = model.load_model()
        assert llm is not None


class TestMetricFactories:
    def test_faithfulness_metric_type(self):
        metric = get_faithfulness_metric()
        assert isinstance(metric, FaithfulnessMetric)

    def test_answer_relevancy_metric_type(self):
        metric = get_answer_relevancy_metric()
        assert isinstance(metric, AnswerRelevancyMetric)

    def test_contextual_relevancy_metric_type(self):
        metric = get_contextual_relevancy_metric()
        assert isinstance(metric, ContextualRelevancyMetric)

    def test_hallucination_metric_type(self):
        metric = get_hallucination_metric()
        assert isinstance(metric, HallucinationMetric)

    def test_custom_threshold(self):
        metric = get_faithfulness_metric(threshold=0.8)
        assert metric.threshold == 0.8

    def test_metric_uses_litellm_model(self):
        metric = get_faithfulness_metric(model="mistral")
        assert isinstance(metric.model, LiteLLMModel)


class TestGetMetrics:
    def test_all_metrics_by_default(self):
        metrics = get_metrics()
        assert len(metrics) == len(METRIC_REGISTRY)

    def test_specific_metrics(self):
        metrics = get_metrics(names=["faithfulness", "hallucination"])
        assert len(metrics) == 2

    def test_invalid_metric_name_skipped(self):
        metrics = get_metrics(names=["faithfulness", "nonexistent"])
        assert len(metrics) == 1

    def test_model_override(self):
        metrics = get_metrics(names=["faithfulness"], model="mistral")
        assert metrics[0].model.get_model_name() == "mistral"
