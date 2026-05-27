"""CLI entry point for the RAG application."""

import argparse
import sys
import uuid
from argparse import Namespace

from dotenv import load_dotenv

load_dotenv()

from app.rag.chain import query
from app.rag.ingest import ingest
from app.tracing import get_langfuse_client, get_langfuse_handler


def cmd_ingest(args: Namespace) -> None:
    ingest(chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    print("Done.")


def cmd_query(args: Namespace) -> None:
    handler = get_langfuse_handler()
    answer = query(
        question=args.question,
        model=args.model,
        callbacks=[handler],
    )
    print(f"\n{answer}")
    langfuse = get_langfuse_client()
    langfuse.flush()


def cmd_chat(args: Namespace) -> None:
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

    langfuse = get_langfuse_client()
    langfuse.flush()
    print("Goodbye.")


def cmd_agent(args: Namespace) -> None:
    from app.agent.graph import run_agent

    handler = get_langfuse_handler()
    if args.verbose:
        print(f"[agent] Question: {args.question}")
        print(f"[agent] Model: {args.model or 'default'}\n")

    answer = run_agent(
        question=args.question,
        model=args.model,
        callbacks=[handler],
    )
    print(f"\n{answer}")
    langfuse = get_langfuse_client()
    langfuse.flush()


def cmd_agent_chat(args: Namespace) -> None:
    from langgraph.checkpoint.memory import MemorySaver

    from app.agent.graph import build_agent

    handler = get_langfuse_handler()
    checkpointer = MemorySaver()
    graph = build_agent(model=args.model, checkpointer=checkpointer)
    thread_id = args.session or str(uuid.uuid4())

    print(f"AgentGuard Chat (session: {thread_id})")
    print("Type 'quit' to exit.\n")

    from langchain_core.messages import HumanMessage

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question or question.lower() in ("quit", "exit", "q"):
            break

        result = graph.invoke(
            {"messages": [HumanMessage(content=question)]},
            config={
                "callbacks": [handler],
                "configurable": {"thread_id": thread_id},
            },
        )

        answer = result["messages"][-1].content
        print(f"\nAssistant: {answer}\n")

    langfuse = get_langfuse_client()
    langfuse.flush()
    print("Goodbye.")


def cmd_evaluate(args: Namespace) -> None:
    from app.eval.deepeval_runner import run_deepeval_evaluation

    metrics = args.metrics.split(",") if args.metrics else None
    run_deepeval_evaluation(
        dataset_name=args.dataset,
        metric_names=metrics,
        model=args.model,
    )


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
    )

    print_comparison_table(results, run_names, args.dataset)


def cmd_seed_dataset(args: Namespace) -> None:
    from scripts.seed_dataset import main as seed_main

    seed_main()


def cmd_online_eval(args: Namespace) -> None:
    from scripts.online_eval_worker import run_once, main as worker_main
    import sys

    sys.argv = ["online-eval"]
    if args.once:
        sys.argv.append("--once")
    if args.reset:
        sys.argv.append("--reset")
    sys.argv += ["--interval", str(args.interval), "--limit", str(args.limit)]
    worker_main()


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentGuard CLI")
    sub = parser.add_subparsers(dest="command")

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest Langfuse docs into Qdrant")
    p_ingest.add_argument("--chunk-size", type=int, default=800)
    p_ingest.add_argument("--chunk-overlap", type=int, default=200)

    # query
    p_query = sub.add_parser("query", help="Ask a single question (RAG chain)")
    p_query.add_argument("question", help="The question to ask")
    p_query.add_argument("--model", default=None, help="LLM model name")
    p_query.add_argument("--session", default=None)
    p_query.add_argument("--user", default=None)

    # chat
    p_chat = sub.add_parser("chat", help="Interactive RAG chat session")
    p_chat.add_argument("--model", default=None, help="LLM model name")
    p_chat.add_argument("--session", default=None)
    p_chat.add_argument("--user", default=None)

    # agent
    p_agent = sub.add_parser("agent", help="Ask a single question (ReAct agent)")
    p_agent.add_argument("question", help="The question to ask")
    p_agent.add_argument("--model", default=None, help="LLM model name")
    p_agent.add_argument("--verbose", action="store_true", help="Show tool calls")

    # agent-chat
    p_achat = sub.add_parser("agent-chat", help="Interactive agent chat with memory")
    p_achat.add_argument("--model", default=None, help="LLM model name")
    p_achat.add_argument("--session", default=None, help="Session ID for conversation memory")

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Run DeepEval metrics against a dataset")
    p_eval.add_argument("--dataset", required=True, help="Langfuse dataset name")
    p_eval.add_argument("--metrics", default=None, help="Comma-separated metric names (default: all)")
    p_eval.add_argument("--model", default=None, help="LLM model for judge metrics")

    # experiment
    p_exp = sub.add_parser("experiment", help="Compare multiple models against a dataset")
    p_exp.add_argument("--dataset", required=True, help="Langfuse dataset name")
    p_exp.add_argument("--models", required=True, help="Comma-separated model names to compare")
    p_exp.add_argument("--metrics", default=None, help="Comma-separated DeepEval metric names (default: all)")
    p_exp.add_argument("--judge-model", default=None, help="Model for DeepEval judge (default: deepeval_model setting)")
    p_exp.add_argument("--run-prefix", default="experiment", help="Prefix for Langfuse run names (default: experiment)")

    # seed-dataset
    sub.add_parser("seed-dataset", help="Create the rag-eval-v1 dataset in Langfuse")

    # online-eval
    p_oe = sub.add_parser("online-eval", help="Continuous eval worker: score new RAG traces automatically")
    p_oe.add_argument("--once", action="store_true", help="Run one pass and exit")
    p_oe.add_argument("--reset", action="store_true", help="Clear state and re-score all recent traces")
    p_oe.add_argument("--interval", type=int, default=30, help="Poll interval in seconds (default: 30)")
    p_oe.add_argument("--limit", type=int, default=50, help="Traces to fetch per poll (default: 50)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "ingest": cmd_ingest,
        "query": cmd_query,
        "chat": cmd_chat,
        "agent": cmd_agent,
        "agent-chat": cmd_agent_chat,
        "evaluate": cmd_evaluate,
        "experiment": cmd_experiment,
        "seed-dataset": cmd_seed_dataset,
        "online-eval": cmd_online_eval,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
