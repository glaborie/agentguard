from argparse import Namespace

from app.cli.common import flush
from app.tracing import get_langfuse_handler


def register(sub) -> None:
    p = sub.add_parser("agent", help="Ask a single question (ReAct agent)")
    p.add_argument("question", help="The question to ask")
    p.add_argument("--model", default=None, help="LLM model name")
    p.add_argument("--session", default=None, help="Langfuse session ID")
    p.add_argument("--user", default=None, help="Langfuse user ID")
    p.add_argument("--verbose", action="store_true", help="Show tool calls")
    p.set_defaults(func=cmd_agent)

    p = sub.add_parser("agent-chat", help="Interactive agent chat with memory")
    p.add_argument("--model", default=None, help="LLM model name")
    p.add_argument("--session", default=None, help="Session ID for conversation memory")
    p.add_argument("--user", default=None, help="Langfuse user ID")
    p.set_defaults(func=cmd_agent_chat)


def cmd_agent(args: Namespace) -> None:
    from app.agent.service import run

    handler = get_langfuse_handler()
    if args.verbose:
        print(f"[agent] Question: {args.question}")
        print(f"[agent] Model: {args.model or 'default'}\n")
    answer = run(
        question=args.question,
        model=args.model,
        callbacks=[handler],
        session_id=args.session,
        user_id=args.user,
    )
    print(f"\n{answer}")
    flush()


def cmd_agent_chat(args: Namespace) -> None:
    from app.agent.service import build_chat_session, respond

    handler = get_langfuse_handler()
    graph, thread_id = build_chat_session(model=args.model, session_id=args.session)

    print(f"AgentGuard Chat (session: {thread_id})")
    print("Type 'quit' to exit.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question or question.lower() in ("quit", "exit", "q"):
            break
        answer = respond(
            graph, thread_id, question, callbacks=[handler], user_id=args.user
        )
        print(f"\nAssistant: {answer}\n")

    flush()
    print("Goodbye.")
