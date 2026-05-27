import json
import logging
import sys
from argparse import Namespace


def register(sub) -> None:
    p = sub.add_parser("regression-gate", help="Run golden dataset through RAG and fail if metrics drop")
    p.add_argument("--dataset", default="rag-golden-set", help="Langfuse dataset name (default: rag-golden-set)")
    p.add_argument("--model", default=None, help="RAG model (default: settings.default_model)")
    p.add_argument("--metrics", default=None, help="Comma-separated metric names (default: all)")
    p.add_argument("--judge-model", default=None, help="DeepEval judge model (default: settings.deepeval_model)")
    p.add_argument("--limit", type=int, default=None, help="Max dataset items (default: all)")
    p.add_argument("--thresholds", default=None, help='JSON overrides e.g. \'{"FaithfulnessMetric":0.85}\'')
    p.add_argument("--run-prefix", default="regression-gate", help="Langfuse run name prefix (default: regression-gate)")
    p.add_argument("--no-push", action="store_true", help="Skip pushing scores to Langfuse")
    p.set_defaults(func=cmd_regression_gate)


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
