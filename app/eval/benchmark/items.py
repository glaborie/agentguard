"""Benchmark data classes and JSONL loaders."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

BENCHMARK_DIR = Path(__file__).parent.parent.parent.parent / "mock_corpus" / "07_benchmark"

RunMode = Literal["full", "no-guardrails", "direct"]


@dataclass
class BenchmarkItem:
    id: str
    question: str
    gold_docs: list[str]
    expected_facts: list[str]
    should_escalate: bool
    expected_action: str
    ideal_answer: str = ""


@dataclass
class BenchmarkResult:
    id: str
    question: str
    answer: str
    mode: RunMode
    retrieved_sources: list[str] = field(default_factory=list)
    retrieval_hit: float = 0.0       # 0/1
    factual_coverage: float = 0.0    # 0.0–1.0
    policy_violation: float = 0.0    # 0/1
    correct_escalation: float = 0.0  # 0/1
    helpfulness: float = 0.0         # 1–5
    policy_reason: str = ""
    helpfulness_reason: str = ""
    error: str = ""


def load_benchmark_items(
    benchmark_dir: Path | None = None,
) -> dict[str, BenchmarkItem]:
    """Load and merge benchmark_questions.jsonl, expected_answers.jsonl,
    and any additional *_questions.jsonl / edge_cases.jsonl files."""
    root = benchmark_dir or BENCHMARK_DIR

    questions: dict[str, dict] = {}
    for f in root.glob("*.jsonl"):
        if "retrieval_labels" in f.name or "expected_answers" in f.name:
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if rec := _parse_line(line):
                questions[rec["id"]] = rec

    answers_file = root / "expected_answers.jsonl"
    if answers_file.exists():
        for line in answers_file.read_text(encoding="utf-8").splitlines():
            if rec := _parse_line(line):
                if rec["id"] in questions:
                    questions[rec["id"]]["ideal_answer"] = rec.get("ideal_answer", "")

    return {
        qid: BenchmarkItem(
            id=qid,
            question=q.get("question", ""),
            gold_docs=q.get("gold_docs", []),
            expected_facts=q.get("expected_facts", []),
            should_escalate=q.get("should_escalate", False),
            expected_action=q.get("expected_action", ""),
            ideal_answer=q.get("ideal_answer", ""),
        )
        for qid, q in sorted(questions.items())
    }


def load_retrieval_labels(benchmark_dir: Path | None = None) -> dict[str, list[str]]:
    root = benchmark_dir or BENCHMARK_DIR
    labels: dict[str, list[str]] = {}
    f = root / "retrieval_labels.jsonl"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if rec := _parse_line(line):
                labels[rec["id"]] = rec.get("relevant_docs", [])
    return labels


def _parse_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None
