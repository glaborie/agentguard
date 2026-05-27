"""Unit tests for scripts.regression_gate (pure logic, no Docker needed)."""

import math

import pytest

from scripts.regression_gate import (
    DEFAULT_THRESHOLDS,
    LOWER_IS_BETTER,
    _check_thresholds,
    _print_report,
)


class TestCheckThresholds:
    def test_all_pass(self):
        avgs = {
            "FaithfulnessMetric": 0.90,
            "AnswerRelevancyMetric": 0.80,
            "ContextualRelevancyMetric": 0.50,
            "HallucinationMetric": 0.10,
        }
        assert _check_thresholds(avgs, DEFAULT_THRESHOLDS) == []

    def test_faithfulness_fails(self):
        avgs = {"FaithfulnessMetric": 0.70}
        failures = _check_thresholds(avgs, DEFAULT_THRESHOLDS)
        assert len(failures) == 1
        assert "FaithfulnessMetric" in failures[0]
        assert "< 0.80" in failures[0]

    def test_hallucination_fails_when_too_high(self):
        avgs = {"HallucinationMetric": 0.50}
        failures = _check_thresholds(avgs, DEFAULT_THRESHOLDS)
        assert len(failures) == 1
        assert "HallucinationMetric" in failures[0]
        assert "> 0.30" in failures[0]

    def test_hallucination_passes_when_low(self):
        avgs = {"HallucinationMetric": 0.05}
        assert _check_thresholds(avgs, DEFAULT_THRESHOLDS) == []

    def test_metric_without_threshold_ignored(self):
        avgs = {"UnknownMetric": 0.0}
        assert _check_thresholds(avgs, DEFAULT_THRESHOLDS) == []

    def test_multiple_failures(self):
        avgs = {
            "FaithfulnessMetric": 0.50,
            "AnswerRelevancyMetric": 0.40,
        }
        failures = _check_thresholds(avgs, DEFAULT_THRESHOLDS)
        assert len(failures) == 2

    def test_threshold_override(self):
        avgs = {"FaithfulnessMetric": 0.85}
        # Raise threshold above the score to force failure
        failures = _check_thresholds(avgs, {"FaithfulnessMetric": 0.90})
        assert len(failures) == 1

    def test_exact_threshold_passes(self):
        avgs = {"FaithfulnessMetric": 0.80}
        assert _check_thresholds(avgs, {"FaithfulnessMetric": 0.80}) == []

    def test_exact_hallucination_threshold_passes(self):
        avgs = {"HallucinationMetric": 0.30}
        assert _check_thresholds(avgs, {"HallucinationMetric": 0.30}) == []


class TestLowerIsBetter:
    def test_hallucination_in_lower_is_better(self):
        assert "HallucinationMetric" in LOWER_IS_BETTER

    def test_faithfulness_not_in_lower_is_better(self):
        assert "FaithfulnessMetric" not in LOWER_IS_BETTER


class TestPrintReport:
    def test_prints_pass_banner(self, capsys):
        _print_report(
            dataset_name="test-set",
            model="test-model",
            run_name="gate-123",
            n_items=3,
            avgs={"FaithfulnessMetric": 0.90},
            thresholds={"FaithfulnessMetric": 0.80},
            failures=[],
            metric_labels=["FaithfulnessMetric"],
        )
        out = capsys.readouterr().out
        assert "GATE PASSED" in out
        assert "FaithfulnessMetric" in out
        assert "PASS" in out

    def test_prints_fail_banner(self, capsys):
        _print_report(
            dataset_name="test-set",
            model="test-model",
            run_name="gate-123",
            n_items=3,
            avgs={"FaithfulnessMetric": 0.70},
            thresholds={"FaithfulnessMetric": 0.80},
            failures=["FaithfulnessMetric: 0.700 < 0.80 (min required)"],
            metric_labels=["FaithfulnessMetric"],
        )
        out = capsys.readouterr().out
        assert "GATE FAILED" in out
        assert "FAIL" in out

    def test_hallucination_shows_max_threshold(self, capsys):
        _print_report(
            dataset_name="test-set",
            model="test-model",
            run_name="gate-123",
            n_items=2,
            avgs={"HallucinationMetric": 0.10},
            thresholds={"HallucinationMetric": 0.30},
            failures=[],
            metric_labels=["HallucinationMetric"],
        )
        out = capsys.readouterr().out
        assert "<= 0.30" in out

    def test_faithfulness_shows_min_threshold(self, capsys):
        _print_report(
            dataset_name="test-set",
            model="test-model",
            run_name="gate-123",
            n_items=2,
            avgs={"FaithfulnessMetric": 0.90},
            thresholds={"FaithfulnessMetric": 0.80},
            failures=[],
            metric_labels=["FaithfulnessMetric"],
        )
        out = capsys.readouterr().out
        assert ">= 0.80" in out
