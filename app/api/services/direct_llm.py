import logging
from typing import Optional

import httpx

from app.core.config import settings
from app.core.ids import completion_id

logger = logging.getLogger(__name__)


async def call(
    messages: list[dict],
    litellm_model: str,
    request_id: str,
    *,
    query: Optional[str] = None,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> tuple[str, str]:
    """Call LiteLLM directly (no RAG context). Returns (result_text, completion_id).

    Guardrails (injection guard + PII masking) still apply because the call
    goes through the LiteLLM proxy.  All httpx errors are caught and returned
    as inline error strings so the caller always gets a string result.
    """
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{settings.litellm_base_url}/v1/chat/completions",
                json={"model": litellm_model, "messages": messages},
                headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            )
        resp.raise_for_status()
        result = resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        logger.error("[%s] LiteLLM HTTP error: %s", request_id, detail)
        result = f"[Error: {detail}] (request_id={request_id})"
        if e.response.status_code == 400:
            from app.api.services.guardrail_scoring import detect_guardrail_type, score_guardrail_block
            gtype = detect_guardrail_type(detail)
            if gtype:
                score_guardrail_block(gtype, query or "", None, chat_id=chat_id, user_id=user_id)
    except httpx.TimeoutException as e:
        logger.error("[%s] LiteLLM request timed out: %s", request_id, e)
        result = f"[Error: upstream timeout] (request_id={request_id})"
    except httpx.RequestError as e:
        logger.error("[%s] LiteLLM unreachable: %s", request_id, e)
        result = f"[Error: upstream unavailable] (request_id={request_id})"
    except Exception as e:
        logger.error("[%s] Unexpected error on direct path: %s", request_id, e)
        result = f"[Error: {e}] (request_id={request_id})"

    return result, completion_id()
