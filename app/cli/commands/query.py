from argparse import Namespace

from app.cli.common import flush
from app.tracing import get_langfuse_handler


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
