import logging
from typing import Optional

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph import build_agent
from app.api.services.guardrail_scoring import detect_guardrail_type, score_guardrail_block
from app.core.config import settings
from app.core.ids import completion_id

logger = logging.getLogger(__name__)

_graph = None
_checkpointer = None


def _get_graph():
    global _graph, _checkpointer
    if _graph is None:
        _checkpointer = MemorySaver()
        _graph = build_agent(model=settings.agent_model, checkpointer=_checkpointer)
    return _graph


def call(
    query: str,
    chat_id: Optional[str],
    user_id: Optional[str],
    request_id: str,
) -> tuple[str, str]:
    """Invoke the ReAct agent for one turn. Returns (answer_text, completion_id)."""
    thread_id = chat_id or request_id
    graph = _get_graph()
    config: dict = {"configurable": {"thread_id": thread_id}}

    try:
        result = graph.invoke({"messages": [HumanMessage(content=query)]}, config=config)
        raw = result["messages"][-1].content
        if isinstance(raw, list):
            answer = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in raw
            )
        else:
            answer = raw
    except Exception as e:
        logger.error("[%s] Agent error: %s", request_id, e)
        answer = f"[Error: {e}] (request_id={request_id})"
        gtype = detect_guardrail_type(e)
        if gtype:
            score_guardrail_block(
                gtype, query, None,
                chat_id=chat_id, user_id=user_id, request_id=request_id,
            )

    return answer, completion_id()
