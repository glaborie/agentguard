"""CLI entry point for the RAG application."""

import argparse
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

from app.rag.chain import query
from app.rag.ingest import ingest
from app.tracing import get_langfuse_client, get_langfuse_handler


def cmd_ingest(args):
    ingest(chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)
    print("Done.")


def cmd_query(args):
    handler = get_langfuse_handler()
    answer = query(
        question=args.question,
        model=args.model,
        callbacks=[handler],
    )
    print(f"\n{answer}")
    langfuse = get_langfuse_client()
    langfuse.flush()


def cmd_chat(args):
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


def cmd_agent(args):
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


def cmd_agent_chat(args):
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


def cmd_evaluate(args):
    from app.eval.deepeval_runner import run_deepeval_evaluation

    metrics = args.metrics.split(",") if args.metrics else None
    run_deepeval_evaluation(
        dataset_name=args.dataset,
        metric_names=metrics,
        model=args.model,
    )


def cmd_seed_dataset(args):
    from scripts.seed_dataset import main as seed_main

    seed_main()


def main():
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

    # seed-dataset
    sub.add_parser("seed-dataset", help="Create the rag-eval-v1 dataset in Langfuse")

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
        "seed-dataset": cmd_seed_dataset,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
