import sys
from argparse import Namespace


def register(sub) -> None:
    p = sub.add_parser("drift-check", help="Detect quality metric regressions from Langfuse score history")
    p.add_argument("--days", type=int, default=14, help="History window in days (default: 14)")
    p.add_argument("--fail-on-regression", action="store_true", help="Exit 1 if any regression detected")
    p.add_argument(
        "--threshold",
        action="append",
        metavar="METRIC=VALUE",
        help="Override threshold for a metric, e.g. --threshold faithfulness=0.03",
    )
    p.set_defaults(func=cmd_drift_check)


def cmd_drift_check(args: Namespace) -> None:
    from app.eval.drift import check_drift, fetch_scores_from_langfuse, print_drift_table

    threshold_overrides: dict[str, float] = {}
    if args.threshold:
        for entry in args.threshold:
            metric, _, val = entry.partition("=")
            threshold_overrides[metric.strip()] = float(val.strip())

    scores = fetch_scores_from_langfuse(days=args.days)
    alerts = check_drift(scores, threshold_overrides=threshold_overrides or None)

    all_metrics = list(scores["metric"].unique()) if not scores.empty else []
    print_drift_table(alerts, all_metrics=all_metrics)

    if alerts:
        print(f"  {len(alerts)} regression(s) detected.")
        if args.fail_on_regression:
            sys.exit(1)
    else:
        print("  No regressions detected.")
