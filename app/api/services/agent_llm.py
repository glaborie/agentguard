import asyncio
import logging
from typing import Optional

from app.agent.graph import run_agent_async
from app.api.services.guardrail_scoring import detect_guardrail_type, score_guardrail_block
from app.core.config import settings
from app.core.ids import completion_id

logger = logging.getLogger(__name__)

def call(
    query: str,
    chat_id: Optional[str],
    user_id: Optional[str],
    request_id: str,
    model: Optional[str] = None,
) -> tuple[str, str]:
    """Invoke the ReAct agent for one turn. Returns (answer_text, completion_id)."""
    resolved_model = model or settings.agent_model

    try:
        raw = asyncio.run(
            run_agent_async(
                question=query,
                model=resolved_model,
                checkpointer=None,
            )
        )
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
