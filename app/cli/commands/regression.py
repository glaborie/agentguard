import json
import logging
import sys
from argparse import Namespace


def cmd_regression_gate(args: Namespace) -> None:
    from scripts.regression_gate import run_gate

    metric_names = [m.strip() for m in args.metrics.split(",")] if args.metrics else None
    thresholds = json.loads(args.thresholds) if args.thresholds else None

    try:
        passed = run_gate(
            dataset_name=args.dataset,
            model=args.model,
            metric_names=metric_names,
            thresholds=thresholds,
            limit=args.limit,
            judge_model=args.judge_model,
            run_prefix=args.run_prefix,
            push_scores=not args.no_push,
        )
    except Exception as exc:
        logging.basicConfig(level=logging.ERROR)
        logging.getLogger(__name__).error("Gate error: %s", exc, exc_info=True)
        sys.exit(2)

    sys.exit(0 if passed else 1)
