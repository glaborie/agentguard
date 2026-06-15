"""LangGraph ReAct agent for AgentGuard."""

import asyncio
import warnings
from typing import Any

from app.core.pii import mask as mask_pii

warnings.filterwarnings(
    "ignore",
    message=r".*allowed_objects.*",
    category=PendingDeprecationWarning,
)

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.mcp_client import load_github_mcp_tools
from app.agent.prompts import AGENT_SYSTEM_PROMPT
from app.agent.tool_guard import ToolCallBlockedError, register_mcp_tools, validate_tool_call
from app.agent.tools import ALL_TOOLS
from app.core.config import settings


def _get_llm(model: str | None = None) -> ChatOpenAI:
    return ChatOpenAI(
        model=model or settings.default_model,
        base_url=f"{settings.litellm_base_url}/v1",
        api_key=settings.litellm_master_key,  # type: ignore[arg-type]
        temperature=0.0,
        metadata={"x-agentguard-internal": True},
    )


async def _agent_node(state: MessagesState, llm_with_tools: Any) -> dict:
    messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT)] + state["messages"]
    response = await llm_with_tools.ainvoke(messages)
    return {"messages": [response]}


def _should_continue(state: MessagesState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


def _make_guarded_tool_node(tools: list) -> Any:
    """Return a guarded node that validates tool calls before dispatching."""
    tool_node = ToolNode(tools)

    async def guarded(state: MessagesState) -> dict:
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
            return {"messages": blocked_messages}

        if blocked_messages:
            result = await tool_node.ainvoke(state)
            result["messages"] = blocked_messages + result.get("messages", [])
            return result

        return await tool_node.ainvoke(state)

    return guarded


def build_agent(
    model: str | None = None,
    checkpointer: Any = None,
    extra_tools: list | None = None,
) -> Any:
    """Build and compile the ReAct agent graph.

    Args:
        model: LLM model name (routes through LiteLLM).
        checkpointer: LangGraph checkpointer for multi-turn memory.
        extra_tools: Additional tools (e.g., MCP tools) to add alongside ALL_TOOLS.
    """
    tools = ALL_TOOLS + (extra_tools or [])
    llm = _get_llm(model)
    llm_with_tools = llm.bind_tools(tools)

    async def agent_node(state: MessagesState) -> dict:
        return await _agent_node(state, llm_with_tools)

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", _make_guarded_tool_node(tools))

    builder.set_entry_point("agent")
    builder.add_conditional_edges("agent", _should_continue, ["tools", END])
    builder.add_edge("tools", "agent")

    return builder.compile(checkpointer=checkpointer)


async def run_agent_async(
    question: str,
    model: str | None = None,
    callbacks: list | None = None,
    thread_id: str | None = None,
    checkpointer: Any = None,
) -> str:
    """Async version of run_agent — loads GitHub MCP tools if token configured."""
    from langchain_core.messages import HumanMessage

    mcp_tools = await load_github_mcp_tools()
    if mcp_tools:
        register_mcp_tools([t.name for t in mcp_tools])

    graph = build_agent(model=model, checkpointer=checkpointer, extra_tools=mcp_tools)

    config: dict = {}
    if callbacks:
        config["callbacks"] = callbacks
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=mask_pii(question))]},
        config=config,
    )

    last_message = result["messages"][-1]
    return last_message.content


def run_agent(
    question: str,
    model: str | None = None,
    callbacks: list | None = None,
    thread_id: str | None = None,
    checkpointer: Any = None,
) -> str:
    """Run the agent on a single question and return the final text response."""
    return asyncio.run(
        run_agent_async(
            question,
            model=model,
            callbacks=callbacks,
            thread_id=thread_id,
            checkpointer=checkpointer,
        )
    )
