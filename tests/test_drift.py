"""Unit tests for check_drift() in app.eval.drift.

Pure unit tests — no Langfuse, no Docker.
"""

import pandas as pd

from app.eval.drift import DriftAlert, check_drift


def _make_scores(
    metric: str,
    baseline_values: list[float],
    current_values: list[float],
    model: str = "test-model",
) -> pd.DataFrame:
    """Build a minimal scores DataFrame with two 7-day windows."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = []
    # baseline window: days -14 to -7
    for i, v in enumerate(baseline_values):
        rows.append({
            "timestamp": now - timedelta(days=14 - i * (7 / max(len(baseline_values), 1))),
            "trace_id": f"trace-base-{i}",
            "metric": metric,
            "value": v,
            "model": model,
        })
    # current window: days -6.5 to -0.5 (keep away from the -7 boundary to avoid clock skew)
    for i, v in enumerate(current_values):
        rows.append({
            "timestamp": now - timedelta(days=6.5 - i * (6 / max(len(current_values), 1))),
            "trace_id": f"trace-curr-{i}",
            "metric": metric,
            "value": v,
            "model": model,
        })
    return pd.DataFrame(rows)


class TestCheckDriftNoRegression:
    def test_stable_faithfulness_no_alert(self):
        df = _make_scores("faithfulness", [0.8, 0.82, 0.79], [0.81, 0.80, 0.83])
        alerts = check_drift(df)
        assert alerts == []

    def test_improving_metric_no_alert(self):
        df = _make_scores("answer_relevancy", [0.6, 0.62, 0.61], [0.75, 0.78, 0.76])
        alerts = check_drift(df)
        assert alerts == []


class TestCheckDriftRegression:
    def test_faithfulness_drop_triggers_alert(self):
        # Drop > default threshold 0.05
        df = _make_scores("faithfulness", [0.85, 0.86, 0.84], [0.75, 0.74, 0.76])
        alerts = check_drift(df)
        assert len(alerts) == 1
        alert = alerts[0]
        assert isinstance(alert, DriftAlert)
        assert alert.metric == "faithfulness"
        assert alert.delta < -0.05
        assert alert.status == "REGRESSION"

    def test_hallucination_increase_triggers_alert(self):
        # hallucination: higher = worse, threshold +0.05
        df = _make_scores("hallucination", [0.1, 0.12, 0.11], [0.25, 0.27, 0.26])
        alerts = check_drift(df)
        assert len(alerts) == 1
        assert alerts[0].metric == "hallucination"
        assert alerts[0].delta > 0.05

    def test_multiple_metrics_multiple_alerts(self):
        df1 = _make_scores("faithfulness", [0.85, 0.86], [0.70, 0.71])
        df2 = _make_scores("answer_relevancy", [0.80, 0.81], [0.65, 0.64])
        df = pd.concat([df1, df2], ignore_index=True)
        alerts = check_drift(df)
        assert len(alerts) == 2
        metrics = {a.metric for a in alerts}
        assert metrics == {"faithfulness", "answer_relevancy"}


class TestCheckDriftThresholdOverride:
    def test_stricter_threshold_catches_smaller_drop(self):
        # Delta ~-0.03 — below default 0.05 but above override 0.02
        df = _make_scores("faithfulness", [0.80, 0.81, 0.82], [0.77, 0.78, 0.78])
        # No alert with default threshold
        assert check_drift(df) == []
        # Alert with stricter threshold
        alerts = check_drift(df, threshold_overrides={"faithfulness": 0.02})
        assert len(alerts) == 1

    def test_looser_threshold_suppresses_alert(self):
        # Delta ~-0.1, default threshold 0.05 would alert
        df = _make_scores("faithfulness", [0.85, 0.86], [0.75, 0.74])
        assert len(check_drift(df)) == 1
        # With loose threshold, no alert
        alerts = check_drift(df, threshold_overrides={"faithfulness": 0.15})
        assert alerts == []


class TestCheckDriftEdgeCases:
    def test_empty_dataframe_returns_empty(self):
        df = pd.DataFrame(columns=["timestamp", "trace_id", "metric", "value", "model"])
        alerts = check_drift(df)
        assert alerts == []

    def test_insufficient_data_skips_metric(self):
        # Only current window data (< 14 days history) — can't compute baseline
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        df = pd.DataFrame([
            {"timestamp": now - timedelta(days=2), "trace_id": "t1", "metric": "faithfulness", "value": 0.8, "model": "m"},
            {"timestamp": now - timedelta(days=1), "trace_id": "t2", "metric": "faithfulness", "value": 0.7, "model": "m"},
        ])
        alerts = check_drift(df)
        assert alerts == []
