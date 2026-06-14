"""Experiments subpackage — public API re-exported for backward compatibility."""

from app.eval.experiments.items import ItemResult
from app.eval.experiments.report import (
    aggregate_costs,
    print_comparison_table,
    print_cost_table,
)
from app.eval.experiments.runner import run_experiment, run_ragas_experiment

__all__ = [
    "ItemResult",
    "run_experiment",
    "run_ragas_experiment",
    "aggregate_costs",
    "print_cost_table",
    "print_comparison_table",
]
