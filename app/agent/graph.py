"""LangGraph ReAct agent for AgentGuard."""

from typing import Any, Literal

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.prompts import AGENT_SYSTEM_PROMPT
from app.agent.tool_guard import ToolCallBlockedError, validate_tool_call
from app.agent.tools import ALL_TOOLS
from app.config import settings


def _get_llm(model: str | None = None) -> ChatOpenAI:
    return ChatOpenAI(
        model=model or settings.default_model,
        base_url=f"{settings.litellm_base_url}/v1",
        api_key=settings.litellm_master_key,
        temperature=0.0,
        default_headers={"x-agentguard-internal": "true"},
    )


def _agent_node(state: MessagesState, llm_with_tools: ChatOpenAI) -> dict:
    messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def _should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


_tool_node = ToolNode(ALL_TOOLS)


def _guarded_tool_node(state: MessagesState) -> dict:
    """Validate each pending tool call before delegating to ToolNode.

    Blocked calls are returned as ToolMessage errors so the agent can
    reason about the refusal rather than crashing the graph.
    """
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", []) or []

    blocked_messages = []
    allowed_calls = []
    for tc in tool_calls:
        tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
        tool_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
        tool_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
        try:
            validate_tool_call(tool_name, tool_args)
            allowed_calls.append(tc)
        except ToolCallBlockedError as exc:
            blocked_messages.append(
                ToolMessage(content=f"[BLOCKED] {exc}", tool_call_id=tool_id or "unknown")
            )

    if blocked_messages and not allowed_calls:
        # All calls blocked — return error messages directly without hitting ToolNode.
        return {"messages": blocked_messages}

    if blocked_messages:
        # Partial block — run allowed calls, prepend block notices.
        result = _tool_node.invoke(state)
        result["messages"] = blocked_messages + result.get("messages", [])
        return result

    return _tool_node.invoke(state)


def build_agent(model: str | None = None, checkpointer: Any = None) -> Any:
    """Build and compile the ReAct agent graph.

    Args:
        model: LLM model name (routes through LiteLLM).
        checkpointer: LangGraph checkpointer for multi-turn memory.
                      Pass MemorySaver() for chat sessions.
    """
    llm = _get_llm(model)
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    def agent_node(state: MessagesState) -> dict:
        return _agent_node(state, llm_with_tools)

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", _guarded_tool_node)

    builder.set_entry_point("agent")
    builder.add_conditional_edges("agent", _should_continue, ["tools", END])
    builder.add_edge("tools", "agent")

    return builder.compile(checkpointer=checkpointer)


def run_agent(
    question: str,
    model: str | None = None,
    callbacks: list | None = None,
    thread_id: str | None = None,
    checkpointer=None,
) -> str:
    """Run the agent on a single question and return the final text response."""
    graph = build_agent(model=model, checkpointer=checkpointer)

    config = {}
    if callbacks:
        config["callbacks"] = callbacks
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    from langchain_core.messages import HumanMessage

    result = graph.invoke(
        {"messages": [HumanMessage(content=question)]},
        config=config,
    )

    last_message = result["messages"][-1]
    return last_message.content
