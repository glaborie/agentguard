import logging
from argparse import Namespace


def register(sub) -> None:
    p = sub.add_parser("experiment", help="Compare multiple models against a dataset")
    p.add_argument("--dataset", required=True, help="Langfuse dataset name")
    p.add_argument("--models", required=True, help="Comma-separated model names to compare")
    p.add_argument("--metrics", default=None, help="Comma-separated DeepEval metric names (default: all)")
    p.add_argument("--judge-model", default=None, help="Model for DeepEval judge (default: deepeval_model setting)")
    p.add_argument("--run-prefix", default="experiment", help="Prefix for Langfuse run names (default: experiment)")
    p.add_argument("--limit", type=int, default=None, help="Max dataset items to evaluate (default: all)")
    p.set_defaults(func=cmd_experiment)


def cmd_experiment(args: Namespace) -> None:
    from app.eval.service import experiment, show_experiment_table

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    models = [m.strip() for m in args.models.split(",")]
    metric_names = [m.strip() for m in args.metrics.split(",")] if args.metrics else None

    print(f"Dataset : {args.dataset}")
    print(f"Models  : {models}")
    print(f"Metrics : {metric_names or 'all (faithfulness, answer_relevancy, contextual_relevancy, hallucination)'}")
    print(f"Judge   : {args.judge_model or 'default (deepeval_model setting)'}\n")

    results, run_names = experiment(
        dataset_name=args.dataset,
        models=models,
        run_prefix=args.run_prefix,
        metric_names=metric_names,
        judge_model=args.judge_model,
        limit=args.limit,
    )
    show_experiment_table(results, run_names, args.dataset)
