"""Quality drift detection: compare metric windows and flag regressions.

Pure function: check_drift() accepts a DataFrame, returns DriftAlert list.
No Langfuse dependency here — callers (notebook, CLI) handle the fetch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd

logger = logging.getLogger(__name__)

# Metrics where higher value = worse outcome (regression = positive delta)
_HIGHER_IS_WORSE = {"hallucination"}

# Default regression thresholds per metric
_DEFAULT_THRESHOLDS: dict[str, float] = {
    "faithfulness": 0.05,
    "answer_relevancy": 0.05,
    "contextual_relevancy": 0.05,
    "hallucination": 0.05,
}
_FALLBACK_THRESHOLD = 0.05


@dataclass
class DriftAlert:
    metric: str
    baseline_mean: float
    current_mean: float
    delta: float
    threshold: float
    status: str  # "REGRESSION" | "OK"


def check_drift(
    scores: pd.DataFrame,
    threshold_overrides: dict[str, float] | None = None,
    window_days: int = 7,
) -> list[DriftAlert]:
    """Detect quality regressions by comparing two consecutive time windows.

    Args:
        scores: DataFrame with columns [timestamp, trace_id, metric, value, model].
                Timestamps must be timezone-naive UTC or timezone-aware.
        threshold_overrides: Per-metric threshold overrides (absolute delta).
        window_days: Size of each comparison window in days (default 7).

    Returns:
        List of DriftAlert for metrics that crossed their regression threshold.
        Empty list if data is insufficient or no regression detected.
    """
    if scores.empty:
        return []

    thresholds = dict(_DEFAULT_THRESHOLDS)
    if threshold_overrides:
        thresholds.update(threshold_overrides)

    now = datetime.now(timezone.utc)
    cutoff_current_start = now - timedelta(days=window_days)
    cutoff_baseline_start = now - timedelta(days=window_days * 2)

    # Normalise timestamps to UTC-aware for comparison
    ts = pd.to_datetime(scores["timestamp"])
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")

    df = scores.copy()
    df["_ts"] = ts

    alerts: list[DriftAlert] = []

    for metric in df["metric"].unique():
        mdf = df[df["metric"] == metric]
        threshold = thresholds.get(metric, _FALLBACK_THRESHOLD)

        baseline = mdf[(mdf["_ts"] >= cutoff_baseline_start) & (mdf["_ts"] < cutoff_current_start)]
        current = mdf[(mdf["_ts"] >= cutoff_current_start) & (mdf["_ts"] <= now)]

        if baseline.empty or current.empty:
            logger.debug("drift: insufficient data for metric=%s, skipping", metric)
            continue

        baseline_mean = float(baseline["value"].mean())
        current_mean = float(current["value"].mean())
        delta = current_mean - baseline_mean

        higher_is_worse = metric in _HIGHER_IS_WORSE
        is_regression = delta > threshold if higher_is_worse else delta < -threshold

        if is_regression:
            alerts.append(DriftAlert(
                metric=metric,
                baseline_mean=baseline_mean,
                current_mean=current_mean,
                delta=delta,
                threshold=threshold,
                status="REGRESSION",
            ))

    return alerts


def fetch_scores_from_langfuse(days: int = 14) -> pd.DataFrame:
    """Fetch eval scores from Langfuse for the past N days.

    Returns DataFrame with columns: timestamp, trace_id, metric, value, model.
    Requires LANGFUSE_* env vars to be set.
    """
    from app.core.tracing import get_langfuse_client

    client = get_langfuse_client()
    score_names = ["faithfulness", "answer_relevancy", "contextual_relevancy", "hallucination"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    rows: list[dict] = []
    for name in score_names:
        page = 1
        while True:
            resp = client.api.scores.get_many(name=name, page=page, limit=100)
            items = resp.data if hasattr(resp, "data") else []
            if not items:
                break
            for s in items:
                ts = getattr(s, "timestamp", None)
                if ts is not None and hasattr(ts, "tzinfo") and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts is not None and ts < cutoff:
                    continue
                rows.append({
                    "timestamp": ts,
                    "trace_id": getattr(s, "trace_id", None),
                    "metric": name,
                    "value": float(s.value),
                    "model": "unknown",
                })
            page += 1

    if not rows:
        return pd.DataFrame(columns=["timestamp", "trace_id", "metric", "value", "model"])
    return pd.DataFrame(rows)


def print_drift_table(alerts: list[DriftAlert], all_metrics: list[str] | None = None) -> None:
    """Print regression summary table to stdout."""
    metrics_to_show = all_metrics or [a.metric for a in alerts]
    alert_map = {a.metric: a for a in alerts}

    col = 22
    sep = "-" * (col + 14 + 14 + 10 + 12)
    print(f"\n  {'Quality Drift Report':}")
    print(f"  {sep}")
    print(f"  {'Metric':<{col}}{'Baseline':>14}{'Current':>14}{'Delta':>10}{'Status':>12}")
    print(f"  {sep}")
    for metric in metrics_to_show:
        if metric in alert_map:
            a = alert_map[metric]
            print(
                f"  {a.metric:<{col}}{a.baseline_mean:>14.3f}{a.current_mean:>14.3f}"
                f"{a.delta:>+10.3f}{'⚠ REGRESSION':>12}"
            )
        else:
            print(f"  {metric:<{col}}{'—':>14}{'—':>14}{'—':>10}{'✅ OK':>12}")
    print(f"  {sep}\n")
