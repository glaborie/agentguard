"""CLI entry point for the RAG application."""

import argparse
import sys

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


def main():
    parser = argparse.ArgumentParser(description="Langfuse RAG POC")
    sub = parser.add_subparsers(dest="command")

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest Langfuse docs into Qdrant")
    p_ingest.add_argument("--chunk-size", type=int, default=800)
    p_ingest.add_argument("--chunk-overlap", type=int, default=200)

    # query
    p_query = sub.add_parser("query", help="Ask a single question")
    p_query.add_argument("question", help="The question to ask")
    p_query.add_argument("--model", default=None, help="LLM model name")
    p_query.add_argument("--session", default=None)
    p_query.add_argument("--user", default=None)

    # chat
    p_chat = sub.add_parser("chat", help="Interactive chat session")
    p_chat.add_argument("--model", default=None, help="LLM model name")
    p_chat.add_argument("--session", default=None)
    p_chat.add_argument("--user", default=None)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    {"ingest": cmd_ingest, "query": cmd_query, "chat": cmd_chat}[args.command](args)


if __name__ == "__main__":
    main()
