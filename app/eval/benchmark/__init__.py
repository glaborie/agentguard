"""Benchmark subpackage — public API re-exported for backward compatibility."""

from app.eval.benchmark.items import (
    BENCHMARK_DIR,
    BenchmarkItem,
    BenchmarkResult,
    RunMode,
    _parse_line,
    load_benchmark_items,
    load_retrieval_labels,
)
from app.eval.benchmark.judges import (
    _get_judge_llm,
    _parse_judge_json,
    eval_helpfulness,
    eval_policy_violation,
)
from app.eval.benchmark.metrics import (
    _posix,
    eval_escalation,
    eval_factual_coverage,
    eval_retrieval_hit,
)
from app.eval.benchmark.report import _agg, print_results
from app.eval.benchmark.runner import _run_direct, _run_rag, run_benchmark

__all__ = [
    "BENCHMARK_DIR",
    "BenchmarkItem",
    "BenchmarkResult",
    "RunMode",
    "load_benchmark_items",
    "load_retrieval_labels",
    "eval_retrieval_hit",
    "eval_factual_coverage",
    "eval_escalation",
    "eval_policy_violation",
    "eval_helpfulness",
    "run_benchmark",
    "print_results",
    "_agg",
    "_parse_line",
    "_posix",
    "_get_judge_llm",
    "_parse_judge_json",
    "_run_rag",
    "_run_direct",
]
