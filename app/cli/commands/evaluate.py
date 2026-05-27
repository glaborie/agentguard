import sys
from argparse import Namespace


def cmd_evaluate(args: Namespace) -> None:
    from app.eval.deepeval_runner import run_deepeval_evaluation

    metrics = args.metrics.split(",") if args.metrics else None
    run_deepeval_evaluation(dataset_name=args.dataset, metric_names=metrics, model=args.model)


def cmd_online_eval(args: Namespace) -> None:
    from scripts.online_eval_worker import main as worker_main

    sys.argv = ["online-eval"]
    if args.once:
        sys.argv.append("--once")
    if args.reset:
        sys.argv.append("--reset")
    sys.argv += ["--interval", str(args.interval), "--limit", str(args.limit)]
    worker_main()
