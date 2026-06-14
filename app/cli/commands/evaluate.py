import sys
from argparse import Namespace

from app.cli.common import cli_span


def register(sub) -> None:
    p = sub.add_parser("evaluate", help="Run DeepEval metrics against a dataset")
    p.add_argument("--dataset", required=True, help="Langfuse dataset name")
    p.add_argument("--metrics", default=None, help="Comma-separated metric names (default: all)")
    p.add_argument("--model", default=None, help="LLM model for judge metrics")
    p.add_argument("--cost-report", action="store_true", help="Print token usage and cost summary after evaluation")
    p.set_defaults(func=cmd_evaluate)

    p2 = sub.add_parser("ragas-experiment", help="Run RAGAS metrics against a Langfuse dataset")
    p2.add_argument("--dataset", required=True, help="Langfuse dataset name (e.g. watsonx-qa)")
    p2.add_argument("--models", required=True, help="Comma-separated model names")
    p2.add_argument("--metrics", default=None, help="Comma-separated RAGAS metric names (default: all)")
    p2.add_argument("--judge-model", default=None, help="Model for RAGAS judge calls")
    p2.add_argument("--limit", type=int, default=None, help="Cap dataset items per run")
    p2.add_argument("--run-prefix", default="ragas-experiment", help="Langfuse run name prefix")
    p2.set_defaults(func=cmd_ragas_experiment)

    p = sub.add_parser("online-eval", help="Continuous eval worker: score new RAG traces automatically")
    p.add_argument("--once", action="store_true", help="Run one pass and exit")
    p.add_argument("--reset", action="store_true", help="Clear state and re-score all recent traces")
    p.add_argument("--interval", type=int, default=30, help="Poll interval in seconds (default: 30)")
    p.add_argument("--limit", type=int, default=50, help="Traces to fetch per poll (default: 50)")
    p.set_defaults(func=cmd_online_eval)


def cmd_evaluate(args: Namespace) -> None:
    from app.eval.service import evaluate

    metrics = args.metrics.split(",") if args.metrics else None
    with cli_span("evaluate", dataset=args.dataset, model=args.model or "default"):
        evaluate(dataset_name=args.dataset, metric_names=metrics, model=args.model, cost_report=args.cost_report)


def cmd_ragas_experiment(args: Namespace) -> None:
    from app.eval.service import ragas_experiment
    from app.eval.experiments import print_comparison_table

    models  = [m.strip() for m in args.models.split(",")]
    metrics = [m.strip() for m in args.metrics.split(",")] if args.metrics else None
    with cli_span("ragas-experiment", dataset=args.dataset, models=",".join(models)):
        results, run_names = ragas_experiment(
            dataset_name=args.dataset,
            models=models,
            run_prefix=args.run_prefix,
            metric_names=metrics,
            judge_model=args.judge_model,
            limit=args.limit,
        )
    print_comparison_table(results, run_names, args.dataset)


def cmd_online_eval(args: Namespace) -> None:
    from scripts.online_eval_worker import main as worker_main

    sys.argv = ["online-eval"]
    if args.once:
        sys.argv.append("--once")
    if args.reset:
        sys.argv.append("--reset")
    sys.argv += ["--interval", str(args.interval), "--limit", str(args.limit)]
    worker_main()
