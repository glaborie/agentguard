import uuid
from typing import Any

from langfuse import propagate_attributes

from app.agent.graph import build_agent
from app.agent.graph import run_agent as _run_agent


def run(
    question: str,
    model: str | None = None,
    callbacks: list | None = None,
    thread_id: str | None = None,
    checkpointer=None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> str:
    with propagate_attributes(
        trace_name="agent-run",
        session_id=session_id,
        user_id=user_id,
        tags=["agent", "cli"],
    ):
        return _run_agent(
            question=question,
            model=model,
            callbacks=callbacks,
            thread_id=thread_id,
            checkpointer=checkpointer,
        )


def build_chat_session(model: str | None = None, session_id: str | None = None) -> tuple[Any, str]:
    """Build a stateful agent session. Returns (graph, thread_id)."""
    from langgraph.checkpoint.memory import MemorySaver

    checkpointer = MemorySaver(allowed_objects=['messages'])
    graph = build_agent(model=model, checkpointer=checkpointer)
    thread_id = session_id or str(uuid.uuid4())
    return graph, thread_id


def respond(
    graph,
    thread_id: str,
    question: str,
    callbacks: list | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> str:
    """Invoke the agent graph for one chat turn."""
    from langchain_core.messages import HumanMessage

    config: dict = {"configurable": {"thread_id": thread_id}}
    if callbacks:
        config["callbacks"] = callbacks
    with propagate_attributes(
        trace_name="agent-chat",
        session_id=session_id or thread_id,
        user_id=user_id,
        tags=["agent", "cli"],
    ):
        result = graph.invoke({"messages": [HumanMessage(content=question)]}, config=config)
    return result["messages"][-1].content
