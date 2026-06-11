"""Unit tests for cost aggregation in app.eval.experiments.

Pure unit tests — no LLM calls, no Docker services.
"""

import pytest

from app.eval.experiments import ItemResult, aggregate_costs


def _make_result(
    model: str,
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    cost_usd: float = 0.001,
    scores: dict | None = None,
) -> ItemResult:
    return ItemResult(
        question="q",
        model=model,
        output="a",
        scores=scores or {},
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cost_usd=cost_usd,
    )


class TestAggregateCosts:
    def test_single_model_single_item(self):
        results = [_make_result("model-a", prompt_tokens=100, completion_tokens=50, cost_usd=0.001)]
        agg = aggregate_costs(results)
        assert "model-a" in agg
        assert int(agg["model-a"]["prompt_tokens"]) == 100
        assert int(agg["model-a"]["completion_tokens"]) == 50
        assert int(agg["model-a"]["total_tokens"]) == 150
        assert float(agg["model-a"]["total_cost_usd"]) == pytest.approx(0.001)
        assert int(agg["model-a"]["n_items"]) == 1

    def test_single_model_multiple_items(self):
        results = [
            _make_result("model-a", prompt_tokens=100, completion_tokens=50, cost_usd=0.001),
            _make_result("model-a", prompt_tokens=200, completion_tokens=100, cost_usd=0.002),
        ]
        agg = aggregate_costs(results)
        assert int(agg["model-a"]["prompt_tokens"]) == 300
        assert int(agg["model-a"]["completion_tokens"]) == 150
        assert float(agg["model-a"]["total_cost_usd"]) == pytest.approx(0.003)
        assert int(agg["model-a"]["n_items"]) == 2

    def test_multiple_models_independent(self):
        results = [
            _make_result("model-a", cost_usd=0.001),
            _make_result("model-b", cost_usd=0.005),
        ]
        agg = aggregate_costs(results)
        assert float(agg["model-a"]["total_cost_usd"]) == pytest.approx(0.001)
        assert float(agg["model-b"]["total_cost_usd"]) == pytest.approx(0.005)

    def test_empty_results(self):
        agg = aggregate_costs([])
        assert agg == {}

    def test_zero_cost_still_tracked(self):
        results = [_make_result("model-a", cost_usd=0.0)]
        agg = aggregate_costs(results)
        assert float(agg["model-a"]["total_cost_usd"]) == 0.0
        assert int(agg["model-a"]["n_items"]) == 1

    def test_cost_per_item_calculation(self):
        results = [
            _make_result("model-a", cost_usd=0.003),
            _make_result("model-a", cost_usd=0.003),
            _make_result("model-a", cost_usd=0.003),
        ]
        agg = aggregate_costs(results)
        n = int(agg["model-a"]["n_items"])
        cost_per_item = float(agg["model-a"]["total_cost_usd"]) / n
        assert cost_per_item == pytest.approx(0.003)

    def test_hidden_params_mock(self):
        """Simulate _hidden_params["response_cost"] pattern per TODO #13 spec."""
        hidden_params = {"response_cost": 0.0042}
        result = _make_result("model-a", cost_usd=hidden_params["response_cost"])
        agg = aggregate_costs([result])
        assert float(agg["model-a"]["total_cost_usd"]) == pytest.approx(0.0042)
