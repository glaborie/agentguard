from argparse import Namespace

from app.cli.common import cli_span, flush
from app.core.tracing import get_langfuse_handler


def register(sub) -> None:
    p = sub.add_parser("query", help="Ask a single question (RAG chain)")
    p.add_argument("question", help="The question to ask")
    p.add_argument("--model", default=None, help="LLM model name")
    p.add_argument("--session", default=None)
    p.add_argument("--user", default=None)
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("chat", help="Interactive RAG chat session")
    p.add_argument("--model", default=None, help="LLM model name")
    p.add_argument("--session", default=None)
    p.add_argument("--user", default=None)
    p.set_defaults(func=cmd_chat)


def cmd_query(args: Namespace) -> None:
    from app.rag.service import query

    handler = get_langfuse_handler()
    with cli_span("cli.query", question=args.question[:120]):
        answer = query(
            question=args.question,
            model=args.model,
            callbacks=[handler],
            session_id=args.session,
            user_id=args.user,
        )
    print(f"\n{answer}")
    flush()


def cmd_chat(args: Namespace) -> None:
    from app.rag.service import query

    handler = get_langfuse_handler()
    print("Langfuse RAG Chat (type 'quit' to exit)\n")
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question or question.lower() in ("quit", "exit", "q"):
            break
        answer = query(
            question=question,
            model=args.model,
            callbacks=[handler],
            session_id=args.session,
            user_id=args.user,
        )
        print(f"\nAssistant: {answer}\n")
    flush()
    print("Goodbye.")
