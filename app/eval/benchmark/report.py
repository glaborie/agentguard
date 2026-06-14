"""Benchmark result formatting and aggregate table printing."""

from __future__ import annotations

from app.eval.benchmark.items import BenchmarkResult, RunMode


def _agg(results: list[BenchmarkResult], mode: RunMode, metric: str) -> float:
    vals = [getattr(r, metric) for r in results if r.mode == mode and not r.error]
    return round(sum(vals) / len(vals), 3) if vals else float("nan")


def print_results(
    results: list[BenchmarkResult],
    modes: list[RunMode],
    show_per_question: bool = True,
) -> None:
    """Print per-question details and an aggregate comparison table."""
    if show_per_question:
        for r in results:
            if r.error:
                print(f"\n[{r.mode}] {r.id} ERROR: {r.error}")
                continue
            print(f"\n[{r.mode}] {r.id}")
            print(f"  Q: {r.question}")
            print(f"  A: {r.answer[:200]}{'...' if len(r.answer) > 200 else ''}")
            print(
                f"  retrieval_hit={r.retrieval_hit:.0f}  "
                f"factual_coverage={r.factual_coverage:.2f}  "
                f"correct_escalation={r.correct_escalation:.0f}  "
                f"policy_violation={r.policy_violation:.0f}  "
                f"helpfulness={r.helpfulness:.1f}"
            )
            if r.policy_reason:
                print(f"  policy: {r.policy_reason}")

    col = 16
    header = f"{'Metric':<28}" + "".join(f"{m:>{col}}" for m in modes)
    print(f"\n{'=' * len(header)}")
    print("Benchmark Summary")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    metrics = [
        ("retrieval_hit_rate",        "retrieval_hit"),
        ("factual_coverage",          "factual_coverage"),
        ("correct_escalation_rate",   "correct_escalation"),
        ("policy_violation_rate",     "policy_violation"),
        ("answer_helpfulness (1–5)",  "helpfulness"),
    ]
    for label, attr in metrics:
        row = f"{label:<28}" + "".join(
            f"{_agg(results, m, attr):>{col}.3f}" for m in modes
        )
        print(row)

    print("=" * len(header))

    n_items = len({r.id for r in results})
    n_errors = sum(1 for r in results if r.error)
    print(f"Items: {n_items}  |  Modes: {', '.join(modes)}  |  Errors: {n_errors}")
