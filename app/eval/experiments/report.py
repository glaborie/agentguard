"""Experiment result aggregation and table printing."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from app.eval.experiments.items import ItemResult


def aggregate_costs(results: list[ItemResult]) -> dict[str, dict[str, float | int]]:
    """Aggregate token usage and cost per model across all results."""
    agg: dict[str, dict[str, float | int]] = defaultdict(lambda: {
        "total_cost_usd": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "n_items": 0,
    })
    for r in results:
        m = r.model
        agg[m]["total_cost_usd"] = float(agg[m]["total_cost_usd"]) + r.cost_usd
        agg[m]["prompt_tokens"] = int(agg[m]["prompt_tokens"]) + r.prompt_tokens
        agg[m]["completion_tokens"] = int(agg[m]["completion_tokens"]) + r.completion_tokens
        agg[m]["total_tokens"] = int(agg[m]["total_tokens"]) + r.total_tokens
        agg[m]["n_items"] = int(agg[m]["n_items"]) + 1
    return dict(agg)


def print_cost_table(results: list[ItemResult], run_names: dict[str, str]) -> None:
    """Print per-model cost and token summary."""
    if not results:
        return
    agg = aggregate_costs(results)
    models = list(run_names.keys())

    display_names = {
        m: (m.split("-", 1)[-1] if m.startswith("openrouter-") else m)
        for m in models
    }
    col_w = max(max(len(d) for d in display_names.values()) + 2, 14)
    label_w = 22
    sep = "-" * (label_w + col_w * len(models) + 2)

    print(f"  {'Cost Summary':}")
    print(f"  {sep}")
    header = f"  {'Metric':<{label_w}}"
    for m in models:
        header += f"{display_names[m]:>{col_w}}"
    print(header)
    print(f"  {sep}")

    _empty: dict[str, float | int] = {
        "total_cost_usd": 0.0, "prompt_tokens": 0,
        "completion_tokens": 0, "total_tokens": 0, "n_items": 1,
    }
    rows = [
        ("Total cost (USD)", lambda d: f"${float(d['total_cost_usd']):.4f}"),
        ("Cost per item (USD)", lambda d: f"${float(d['total_cost_usd']) / max(int(d['n_items']), 1):.4f}"),
        ("Prompt tokens", lambda d: str(int(d['prompt_tokens']))),
        ("Completion tokens", lambda d: str(int(d['completion_tokens']))),
        ("Total tokens", lambda d: str(int(d['total_tokens']))),
    ]
    for label, fmt in rows:
        row = f"  {label:<{label_w}}"
        for m in models:
            val = fmt(agg.get(m, _empty))
            row += f"{val:>{col_w}}"
        print(row)

    print(f"  {sep}\n")


def print_comparison_table(
    results: list[ItemResult],
    run_names: dict[str, str],
    dataset_name: str,
) -> None:
    """Print a per-model average score table to stdout."""
    models = list(run_names.keys())

    # Collect metric names in insertion order.
    metric_names: list[str] = []
    for r in results:
        for k in r.scores:
            if k not in metric_names:
                metric_names.append(k)

    # Aggregate per model and metric.
    agg: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        for metric, score in r.scores.items():
            agg[r.model][metric].append(score)

    avgs: dict[str, dict[str, float]] = {
        model: {
            m: (sum(agg[model][m]) / len(agg[model][m])) if agg[model][m] else float("nan")
            for m in metric_names
        }
        for model in models
    }

    display_names = {
        m: (m.split("-", 1)[-1] if m.startswith("openrouter-") else m)
        for m in models
    }
    label_w = max((len(m) for m in metric_names), default=10) + 2
    col_w = max(max(len(d) for d in display_names.values()) + 2, 10)
    sep = "-" * (label_w + col_w * len(models) + 2)

    n_items = len(results) // max(len(models), 1)
    print(f"\n{'=' * (len(sep) + 2)}")
    print(f"  Experiment  : {dataset_name}")
    print(f"  Run at      : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Evaluations : {len(results)}  ({n_items} items x {len(models)} models)")
    print(f"  {sep}")

    header = f"  {'Metric':<{label_w}}"
    for m in models:
        header += f"{display_names[m]:>{col_w}}"
    print(header)
    print(f"  {sep}")

    for metric in metric_names:
        row = f"  {metric:<{label_w}}"
        for m in models:
            v = avgs[m].get(metric, float("nan"))
            row += f"{v:>{col_w}.2f}"
        print(row)

    print(f"  {sep}")
    row = f"  {'AVERAGE':<{label_w}}"
    for m in models:
        all_scores = [s for scores in agg[m].values() for s in scores]
        overall = sum(all_scores) / len(all_scores) if all_scores else float("nan")
        row += f"{overall:>{col_w}.2f}"
    print(row)

    print(f"  {sep}")
    print("  Langfuse dataset runs:")
    for m, run_name in run_names.items():
        print(f"    {run_name}")
    print(f"{'=' * (len(sep) + 2)}\n")

    print_cost_table(results, run_names)
