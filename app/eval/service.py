from app.eval.deepeval_runner import run_deepeval_evaluation
from app.eval.experiments import print_comparison_table, run_experiment


def evaluate(
    dataset_name: str,
    metric_names: list[str] | None = None,
    model: str | None = None,
    cost_report: bool = False,
) -> None:
    run_deepeval_evaluation(dataset_name=dataset_name, metric_names=metric_names, model=model, cost_report=cost_report)


def experiment(
    dataset_name: str,
    models: list[str],
    run_prefix: str = "experiment",
    metric_names: list[str] | None = None,
    judge_model: str | None = None,
    limit: int | None = None,
) -> tuple:
    return run_experiment(
        dataset_name=dataset_name,
        models=models,
        run_prefix=run_prefix,
        metric_names=metric_names,
        judge_model=judge_model,
        limit=limit,
    )


def show_experiment_table(results, run_names: dict, dataset_name: str) -> None:
    print_comparison_table(results, run_names, dataset_name)


def regression_gate(
    dataset_name: str = "rag-golden-set",
    model: str | None = None,
    metric_names: list[str] | None = None,
    thresholds: dict | None = None,
    limit: int | None = None,
    judge_model: str | None = None,
    run_prefix: str = "regression-gate",
    push_scores: bool = True,
) -> bool:
    from scripts.regression_gate import run_gate

    return run_gate(
        dataset_name=dataset_name,
        model=model,
        metric_names=metric_names,
        thresholds=thresholds,
        limit=limit,
        judge_model=judge_model,
        run_prefix=run_prefix,
        push_scores=push_scores,
    )
