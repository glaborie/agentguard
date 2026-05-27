import uuid
from argparse import Namespace

from app.cli.common import flush
from app.tracing import get_langfuse_handler


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
