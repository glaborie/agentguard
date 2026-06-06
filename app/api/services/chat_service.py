import asyncio
import time

from opentelemetry import trace as otel_trace

from app.api.schemas import ChatRequest
from app.api.services import agent_llm, direct_llm, rag_llm
from app.api.services.models_service import AGENT_MODELS, DIRECT_MODELS, MODELS
from app.core.telemetry import get_otel_trace_id


def build_trace_metadata(body: ChatRequest, otel_tid: str | None) -> dict[str, str]:
    metadata: dict[str, str] = {"owui_model": body.model}
    if body.message_id:
        metadata["message_id"] = body.message_id
    if body.user_name:
        metadata["user_name"] = body.user_name
    if otel_tid:
        metadata["otel_trace_id"] = otel_tid
    return metadata


def annotate_span(body: ChatRequest, chat_id: str | None) -> None:
    """Set OTel span attributes so Jaeger shows model, RAG mode, and session."""
    span = otel_trace.get_current_span()
    span.set_attribute("app.model", body.model)
    span.set_attribute("app.is_rag", body.model not in DIRECT_MODELS and body.model not in AGENT_MODELS)
    if chat_id:
        span.set_attribute("app.chat_id", chat_id)


async def complete(
    body: ChatRequest,
    query: str,
    chat_id: str | None,
    request_id: str,
) -> tuple[str, str]:
    """Orchestrate direct or RAG completion. Returns (result_text, completion_id)."""
    litellm_model = MODELS.get(body.model, "openrouter-gemini-flash")
    trace_metadata = build_trace_metadata(body, get_otel_trace_id())
    annotate_span(body, chat_id)

    if body.model in AGENT_MODELS:
        return await asyncio.to_thread(
            agent_llm.call,
            query=query,
            chat_id=chat_id,
            user_id=body.user_id,
            request_id=request_id,
        )

    if body.model in DIRECT_MODELS:
        return await direct_llm.call(
            [m.model_dump() for m in body.messages],
            litellm_model,
            request_id,
            query=query,
            chat_id=chat_id,
            user_id=body.user_id,
        )

    return await rag_llm.call(
        query,
        litellm_model,
        chat_id,
        body.user_id,
        trace_metadata,
        request_id,
    )


def build_completion_response(completion_id: str, model: str, result: str) -> dict[str, object]:
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
