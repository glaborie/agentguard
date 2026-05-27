from opentelemetry import trace as otel_trace

from app.api.routes.models import DIRECT_MODELS, MODELS
from app.api.schemas import ChatRequest
from app.api.services import direct_llm, rag_llm
from app.core.telemetry import get_otel_trace_id


def build_trace_metadata(body: ChatRequest, otel_tid: str | None) -> dict:
    metadata: dict = {"owui_model": body.model}
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
    span.set_attribute("app.is_rag", body.model not in DIRECT_MODELS)
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

    if body.model in DIRECT_MODELS:
        return await direct_llm.call(
            [m.model_dump() for m in body.messages],
            litellm_model,
            request_id,
        )

    return await rag_llm.call(
        query,
        litellm_model,
        chat_id,
        body.user_id,
        trace_metadata,
        request_id,
    )
