"""CLI command handlers — one function per subcommand."""

import json
import logging
import sys
import uuid
from argparse import Namespace

from app.cli.common import flush
from app.tracing import get_langfuse_handler


def cmd_ingest(args: Namespace) -> None:
    from app.rag.ingest import ingest

    ingest(chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    print("Done.")


def cmd_query(args: Namespace) -> None:
    from app.rag.chain import query

    handler = get_langfuse_handler()
    answer = query(question=args.question, model=args.model, callbacks=[handler])
    print(f"\n{answer}")
    flush()


def cmd_chat(args: Namespace) -> None:
    from app.rag.chain import query

    handler = get_langfuse_handler()
    print("Langfuse RAG Chat (type 'quit' to exit)\n")
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question or question.lower() in ("quit", "exit", "q"):
            break
        answer = query(question=question, model=args.model, callbacks=[handler])
        print(f"\nAssistant: {answer}\n")
    flush()
    print("Goodbye.")


def cmd_agent(args: Namespace) -> None:
    from app.agent.graph import run_agent

    handler = get_langfuse_handler()
    if args.verbose:
        print(f"[agent] Question: {args.question}")
        print(f"[agent] Model: {args.model or 'default'}\n")
    answer = run_agent(question=args.question, model=args.model, callbacks=[handler])
    print(f"\n{answer}")
    flush()


def cmd_agent_chat(args: Namespace) -> None:
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import MemorySaver

    from app.agent.graph import build_agent

    handler = get_langfuse_handler()
    checkpointer = MemorySaver()
    graph = build_agent(model=args.model, checkpointer=checkpointer)
    thread_id = args.session or str(uuid.uuid4())

    print(f"AgentGuard Chat (session: {thread_id})")
    print("Type 'quit' to exit.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question or question.lower() in ("quit", "exit", "q"):
            break

        result = graph.invoke(
            {"messages": [HumanMessage(content=question)]},
            config={"callbacks": [handler], "configurable": {"thread_id": thread_id}},
        )
        answer = result["messages"][-1].content
        print(f"\nAssistant: {answer}\n")

    flush()
    print("Goodbye.")


def cmd_evaluate(args: Namespace) -> None:
    from app.eval.deepeval_runner import run_deepeval_evaluation

    metrics = args.metrics.split(",") if args.metrics else None
    run_deepeval_evaluation(dataset_name=args.dataset, metric_names=metrics, model=args.model)


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


def cmd_seed_dataset(args: Namespace) -> None:
    from scripts.seed_dataset import main as seed_main

    seed_main()


def cmd_online_eval(args: Namespace) -> None:
    from scripts.online_eval_worker import main as worker_main

    sys.argv = ["online-eval"]
    if args.once:
        sys.argv.append("--once")
    if args.reset:
        sys.argv.append("--reset")
    sys.argv += ["--interval", str(args.interval), "--limit", str(args.limit)]
    worker_main()


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
