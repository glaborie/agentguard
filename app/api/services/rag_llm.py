import logging

import httpx
from langfuse import propagate_attributes

from app.core.ids import completion_id
from app.core.tracing import get_langfuse_handler
from app.rag.chain import build_rag_chain

logger = logging.getLogger(__name__)


async def call(
    query: str,
    litellm_model: str,
    chat_id: str | None,
    user_id: str | None,
    trace_metadata: dict,
    request_id: str,
) -> tuple[str, str]:
    """Invoke the RAG chain and return (result_text, completion_id).

    Uses the Langfuse trace ID as the completion ID so Open WebUI stores it
    as the message ID for feedback correlation.  All httpx errors are caught
    and returned as inline error strings.
    """
    handler = get_langfuse_handler()
    chain = build_rag_chain(model=litellm_model)
    try:
        with propagate_attributes(
            session_id=chat_id,
            user_id=user_id,
            metadata=trace_metadata,
        ):
            result = chain.invoke(query, config={"callbacks": [handler]})
    except httpx.TimeoutException as e:
        logger.error("[%s] RAG chain timed out calling LiteLLM: %s", request_id, e)
        result = f"[Error: upstream timeout] (request_id={request_id})"
    except httpx.RequestError as e:
        logger.error("[%s] RAG chain could not reach LiteLLM: %s", request_id, e)
        result = f"[Error: upstream unavailable] (request_id={request_id})"
    except Exception as e:
        logger.error("[%s] RAG chain error: %s", request_id, e)
        result = f"[Error: {e}] (request_id={request_id})"

    trace_id = handler.last_trace_id
    return result, trace_id if trace_id else completion_id()
