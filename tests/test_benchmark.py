"""Tests for the NorthstarCRM benchmark runner (app.eval.benchmark).

All tests are pure unit tests — no LLM calls, no Docker, no filesystem outside tmp_path.
The three run modes (full, no-guardrails, direct) are integration-only.
"""

import json
from pathlib import Path

import pytest

from app.eval.benchmark import (
    BenchmarkItem,
    BenchmarkResult,
    _agg,
    eval_escalation,
    eval_factual_coverage,
    eval_retrieval_hit,
    load_benchmark_items,
    load_retrieval_labels,
    print_results,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


@pytest.fixture
def benchmark_dir(tmp_path):
    _write_jsonl(tmp_path / "benchmark_questions.jsonl", [
        {
            "id": "t001",
            "question": "Do you support SAML SSO on Starter?",
            "gold_docs": ["plans-and-pricing.md", "feature-matrix.md"],
            "expected_facts": ["Starter does not include SAML SSO"],
            "should_escalate": False,
            "expected_action": "answer_and_offer_upgrade",
        },
        {
            "id": "t002",
            "question": "Can I get 30% off without approval?",
            "gold_docs": ["discount-policy.md"],
            "expected_facts": ["Discounts above 15% require VP approval"],
            "should_escalate": True,
            "expected_action": "escalate_to_ae",
        },
    ])
    _write_jsonl(tmp_path / "expected_answers.jsonl", [
        {"id": "t001", "ideal_answer": "Starter does not include SAML SSO."},
    ])
    _write_jsonl(tmp_path / "retrieval_labels.jsonl", [
        {"id": "t001", "relevant_docs": ["02_products/plans-and-pricing.md", "02_products/feature-matrix.md"]},
        {"id": "t002", "relevant_docs": ["04_policies/discount-policy.md"]},
    ])
    return tmp_path


# ── Loaders ─────────────────────────────────────────────────────────────────

class TestLoadBenchmarkItems:
    def test_loads_questions(self, benchmark_dir):
        items = load_benchmark_items(benchmark_dir)
        assert "t001" in items and "t002" in items

    def test_merges_ideal_answer(self, benchmark_dir):
        items = load_benchmark_items(benchmark_dir)
        assert "Starter" in items["t001"].ideal_answer

    def test_expected_facts_parsed(self, benchmark_dir):
        items = load_benchmark_items(benchmark_dir)
        assert items["t001"].expected_facts == ["Starter does not include SAML SSO"]

    def test_should_escalate_parsed(self, benchmark_dir):
        items = load_benchmark_items(benchmark_dir)
        assert items["t001"].should_escalate is False
        assert items["t002"].should_escalate is True

    def test_loads_edge_cases_file(self, tmp_path):
        _write_jsonl(tmp_path / "benchmark_questions.jsonl", [
            {"id": "b001", "question": "Q", "gold_docs": [], "expected_facts": [],
             "should_escalate": False, "expected_action": ""},
        ])
        _write_jsonl(tmp_path / "edge_cases.jsonl", [
            {"id": "e001", "question": "Edge Q", "gold_docs": [], "expected_facts": [],
             "should_escalate": True, "expected_action": ""},
        ])
        items = load_benchmark_items(tmp_path)
        assert "b001" in items and "e001" in items

    def test_empty_directory_returns_empty(self, tmp_path):
        items = load_benchmark_items(tmp_path)
        assert items == {}


class TestLoadRetrievalLabels:
    def test_loads_labels(self, benchmark_dir):
        labels = load_retrieval_labels(benchmark_dir)
        assert labels["t001"] == ["02_products/plans-and-pricing.md", "02_products/feature-matrix.md"]

    def test_missing_file_returns_empty(self, tmp_path):
        labels = load_retrieval_labels(tmp_path)
        assert labels == {}


# ── eval_retrieval_hit ───────────────────────────────────────────────────────

class TestEvalRetrievalHit:
    def test_exact_path_match(self):
        assert eval_retrieval_hit(
            ["02_products/plans-and-pricing.md"],
            ["02_products/plans-and-pricing.md"],
        ) == 1.0

    def test_filename_only_match(self):
        assert eval_retrieval_hit(
            ["02_products/plans-and-pricing.md"],
            ["plans-and-pricing.md"],
        ) == 1.0

    def test_partial_match_counts(self):
        # Only one gold doc needs to hit
        assert eval_retrieval_hit(
            ["02_products/plans-and-pricing.md", "other.md"],
            ["plans-and-pricing.md", "missing-doc.md"],
        ) == 1.0

    def test_no_match(self):
        assert eval_retrieval_hit(
            ["02_products/product-overview.md"],
            ["discount-policy.md"],
        ) == 0.0

    def test_empty_gold_docs_vacuously_true(self):
        assert eval_retrieval_hit(["anything.md"], []) == 1.0

    def test_empty_retrieved(self):
        assert eval_retrieval_hit([], ["plans-and-pricing.md"]) == 0.0


# ── eval_factual_coverage ────────────────────────────────────────────────────

class TestEvalFactualCoverage:
    def test_full_coverage(self):
        answer = "Starter does not include SAML SSO. Business and Enterprise plans do."
        facts = ["Starter does not include SAML SSO"]
        assert eval_factual_coverage(answer, facts) == 1.0

    def test_partial_coverage(self):
        answer = "Starter does not include SAML SSO."
        facts = [
            "Starter does not include SAML SSO",
            "VP approval required for discounts above 15%",
        ]
        result = eval_factual_coverage(answer, facts)
        assert 0.0 < result < 1.0

    def test_no_coverage(self):
        answer = "We offer great support."
        facts = ["SAML SSO requires Business or Enterprise plan"]
        assert eval_factual_coverage(answer, facts) == 0.0

    def test_empty_facts_vacuously_true(self):
        assert eval_factual_coverage("anything", []) == 1.0

    def test_case_insensitive(self):
        answer = "starter does not include saml sso"
        assert eval_factual_coverage(answer, ["Starter SAML SSO"]) == 1.0


# ── eval_escalation ──────────────────────────────────────────────────────────

class TestEvalEscalation:
    def test_correct_escalation_when_expected(self):
        answer = "I'll connect you with our sales team to discuss this further."
        assert eval_escalation(answer, should_escalate=True) == 1.0

    def test_missed_escalation(self):
        answer = "Sure, we can give you a 30% discount right now."
        assert eval_escalation(answer, should_escalate=True) == 0.0

    def test_correct_non_escalation(self):
        answer = "Starter does not include SAML SSO. Business and Enterprise plans do."
        assert eval_escalation(answer, should_escalate=False) == 1.0

    def test_unnecessary_escalation(self):
        # Should answer directly, but escalated anyway
        answer = "Please reach out to our sales team for this information."
        assert eval_escalation(answer, should_escalate=False) == 0.0

    @pytest.mark.parametrize("phrase", [
        "contact us", "schedule a call", "account executive",
        "speak with", "escalate", "sales team",
    ])
    def test_escalation_phrase_detection(self, phrase):
        answer = f"We would need to {phrase} to handle this request."
        assert eval_escalation(answer, should_escalate=True) == 1.0


# ── _agg helper ──────────────────────────────────────────────────────────────

class TestAggHelper:
    def _make_results(self):
        return [
            BenchmarkResult(id="q1", question="", answer="", mode="full",
                            retrieval_hit=1.0, factual_coverage=0.8, policy_violation=0.0,
                            correct_escalation=1.0, helpfulness=4.0),
            BenchmarkResult(id="q2", question="", answer="", mode="full",
                            retrieval_hit=0.0, factual_coverage=0.6, policy_violation=1.0,
                            correct_escalation=0.0, helpfulness=2.0),
            BenchmarkResult(id="q3", question="", answer="", mode="no-guardrails",
                            retrieval_hit=1.0, factual_coverage=0.5, policy_violation=0.0,
                            correct_escalation=1.0, helpfulness=3.0),
        ]

    def test_aggregates_by_mode(self):
        results = self._make_results()
        assert _agg(results, "full", "retrieval_hit") == pytest.approx(0.5)
        assert _agg(results, "no-guardrails", "retrieval_hit") == pytest.approx(1.0)

    def test_skips_error_results(self):
        results = self._make_results()
        results[0].error = "something went wrong"
        assert _agg(results, "full", "retrieval_hit") == pytest.approx(0.0)

    def test_empty_returns_nan(self):
        import math
        assert math.isnan(_agg([], "full", "retrieval_hit"))


# ── CLI wiring ───────────────────────────────────────────────────────────────

class TestBenchmarkCLI:
    def test_benchmark_command_registered(self):
        from app.cli.app import _build_parser
        args = _build_parser().parse_args(["benchmark"])
        assert args.command == "benchmark"

    def test_default_mode(self):
        from app.cli.app import _build_parser
        args = _build_parser().parse_args(["benchmark"])
        assert args.mode == "full"
        assert args.compare is False

    def test_compare_flag(self):
        from app.cli.app import _build_parser
        args = _build_parser().parse_args(["benchmark", "--compare"])
        assert args.compare is True

    def test_limit_flag(self):
        from app.cli.app import _build_parser
        args = _build_parser().parse_args(["benchmark", "--limit", "5"])
        assert args.limit == 5

    def test_no_llm_judge_flag(self):
        from app.cli.app import _build_parser
        args = _build_parser().parse_args(["benchmark", "--no-llm-judge"])
        assert args.no_llm_judge is True

    def test_mode_choices(self):
        from app.cli.app import _build_parser
        for mode in ("full", "no-guardrails", "direct"):
            args = _build_parser().parse_args(["benchmark", "--mode", mode])
            assert args.mode == mode
