import logging
from argparse import Namespace


def cmd_experiment(args: Namespace) -> None:
    from app.eval.experiments import print_comparison_table, run_experiment

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    models = [m.strip() for m in args.models.split(",")]
    metric_names = [m.strip() for m in args.metrics.split(",")] if args.metrics else None

    print(f"Dataset : {args.dataset}")
    print(f"Models  : {models}")
    print(f"Metrics : {metric_names or 'all (faithfulness, answer_relevancy, contextual_relevancy, hallucination)'}")
    print(f"Judge   : {args.judge_model or 'default (deepeval_model setting)'}\n")

    results, run_names = run_experiment(
        dataset_name=args.dataset,
        models=models,
        run_prefix=args.run_prefix,
        metric_names=metric_names,
        judge_model=args.judge_model,
        limit=args.limit,
    )
    print_comparison_table(results, run_names, args.dataset)
