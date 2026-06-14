"""DeepEval metric configuration with LiteLLM model wrapper."""

from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
    HallucinationMetric,
)
from deepeval.models import DeepEvalBaseLLM
from langchain_openai import ChatOpenAI

from app.core.config import settings


class LiteLLMModel(DeepEvalBaseLLM):
    """Routes DeepEval judge calls through the LiteLLM proxy."""

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or settings.deepeval_model or settings.default_model
        self._llm = ChatOpenAI(
            model=self._model_name,
            base_url=f"{settings.litellm_base_url}/v1",
            api_key=settings.litellm_master_key,
            temperature=0.0,
            extra_body={"guardrails": []},  # judge prompts contain phrases that trip content guardrails
        )

    def load_model(self) -> ChatOpenAI:
        return self._llm

    def generate(self, prompt: str) -> str:
        return self._llm.invoke(prompt).content

    async def a_generate(self, prompt: str) -> str:
        result = await self._llm.ainvoke(prompt)
        return result.content

    def get_model_name(self) -> str:
        return self._model_name


def get_faithfulness_metric(model: str | None = None, threshold: float = 0.5) -> FaithfulnessMetric:
    return FaithfulnessMetric(model=LiteLLMModel(model), threshold=threshold)


def get_answer_relevancy_metric(model: str | None = None, threshold: float = 0.5) -> AnswerRelevancyMetric:
    return AnswerRelevancyMetric(model=LiteLLMModel(model), threshold=threshold)


def get_contextual_relevancy_metric(model: str | None = None, threshold: float = 0.5) -> ContextualRelevancyMetric:
    return ContextualRelevancyMetric(model=LiteLLMModel(model), threshold=threshold)


def get_hallucination_metric(model: str | None = None, threshold: float = 0.5) -> HallucinationMetric:
    return HallucinationMetric(model=LiteLLMModel(model), threshold=threshold)


METRIC_REGISTRY = {
    "faithfulness": get_faithfulness_metric,
    "answer_relevancy": get_answer_relevancy_metric,
    "contextual_relevancy": get_contextual_relevancy_metric,
    "hallucination": get_hallucination_metric,
}


def get_metrics(names: list[str] | None = None, model: str | None = None) -> list:
    """Return a list of configured DeepEval metrics.

    Args:
        names: Metric names to include. None = all metrics.
        model: Override model for the judge LLM.
    """
    if names is None:
        names = list(METRIC_REGISTRY.keys())
    return [METRIC_REGISTRY[n](model=model) for n in names if n in METRIC_REGISTRY]
