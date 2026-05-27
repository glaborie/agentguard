import logging
import time
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langfuse import propagate_attributes
from opentelemetry import trace as otel_trace

from app.api.routes.models import DIRECT_MODELS, MODELS
from app.api.schemas import ChatRequest
from app.api.streaming import stream_from_result
from app.config import settings
from app.rag.chain import build_rag_chain
from app.telemetry import get_otel_trace_id
from app.tracing import get_langfuse_handler

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/v1/chat/completions")
async def chat_completions(body: ChatRequest, request: Request):
    request_id = uuid.uuid4().hex[:12]

    user_messages = [m for m in body.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    query = user_messages[-1].content
    litellm_model = MODELS.get(body.model, "openrouter-gemini-flash")

    # Open WebUI sends the chat UUID either in the "chat-id" header (older builds)
    # or via the Langfuse Session Linker filter which injects it into the body.
    chat_id: Optional[str] = request.headers.get("chat-id") or body.chat_id
    trace_metadata: dict = {"owui_model": body.model}
    if body.message_id:
        trace_metadata["message_id"] = body.message_id
    if body.user_name:
        trace_metadata["user_name"] = body.user_name

    # Annotate the active OTel span so Jaeger shows model, RAG mode, and session.
    span = otel_trace.get_current_span()
    span.set_attribute("app.model", body.model)
    span.set_attribute("app.is_rag", body.model not in DIRECT_MODELS)
    if chat_id:
        span.set_attribute("app.chat_id", chat_id)

    # Cross-link OTel trace into Langfuse metadata so both systems are navigable.
    otel_tid = get_otel_trace_id()
    if otel_tid:
        trace_metadata["otel_trace_id"] = otel_tid

    if body.model in DIRECT_MODELS:
        # ── Direct LiteLLM path (no RAG context) ─────────────────────────────
        # Guardrails (injection guard + PII masking) still apply because the
        # call goes through the LiteLLM proxy.
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{settings.litellm_base_url}/v1/chat/completions",
                    json={
                        "model": litellm_model,
                        "messages": [m.model_dump() for m in body.messages],
                    },
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
        except httpx.TimeoutException as e:
            logger.error("[%s] LiteLLM request timed out: %s", request_id, e)
            result = f"[Error: upstream timeout] (request_id={request_id})"
        except httpx.RequestError as e:
            logger.error("[%s] LiteLLM unreachable: %s", request_id, e)
            result = f"[Error: upstream unavailable] (request_id={request_id})"
        except Exception as e:
            logger.error("[%s] Unexpected error on direct path: %s", request_id, e)
            result = f"[Error: {e}] (request_id={request_id})"
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    else:
        # ── RAG chain path ────────────────────────────────────────────────────
        handler = get_langfuse_handler()
        chain = build_rag_chain(model=litellm_model)
        try:
            with propagate_attributes(
                session_id=chat_id,
                user_id=body.user_id,
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

        # Use the Langfuse trace ID as the completion ID so Open WebUI stores
        # it as the message ID for feedback correlation.
        trace_id = handler.last_trace_id
        completion_id = trace_id if trace_id else f"chatcmpl-{uuid.uuid4().hex[:8]}"

    if body.stream:
        return StreamingResponse(
            stream_from_result(result, completion_id, body.model),
            media_type="text/event-stream",
        )

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
