import sys
from argparse import Namespace


def register(sub) -> None:
    p = sub.add_parser("evaluate", help="Run DeepEval metrics against a dataset")
    p.add_argument("--dataset", required=True, help="Langfuse dataset name")
    p.add_argument("--metrics", default=None, help="Comma-separated metric names (default: all)")
    p.add_argument("--model", default=None, help="LLM model for judge metrics")
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("online-eval", help="Continuous eval worker: score new RAG traces automatically")
    p.add_argument("--once", action="store_true", help="Run one pass and exit")
    p.add_argument("--reset", action="store_true", help="Clear state and re-score all recent traces")
    p.add_argument("--interval", type=int, default=30, help="Poll interval in seconds (default: 30)")
    p.add_argument("--limit", type=int, default=50, help="Traces to fetch per poll (default: 50)")
    p.set_defaults(func=cmd_online_eval)


def cmd_evaluate(args: Namespace) -> None:
    from app.eval.service import evaluate

    metrics = args.metrics.split(",") if args.metrics else None
    evaluate(dataset_name=args.dataset, metric_names=metrics, model=args.model)


def cmd_online_eval(args: Namespace) -> None:
    from scripts.online_eval_worker import main as worker_main

    sys.argv = ["online-eval"]
    if args.once:
        sys.argv.append("--once")
    if args.reset:
        sys.argv.append("--reset")
    sys.argv += ["--interval", str(args.interval), "--limit", str(args.limit)]
    worker_main()
