"""OpenAI-compatible FastAPI wrapper around the RAG chain.

Exposes /v1/models and /v1/chat/completions so Open WebUI (or any
OpenAI-compatible client) can use the RAG pipeline without knowing about
Qdrant or embeddings.  Three virtual models are exposed:

  agentguard-rag         → openrouter-gemini-flash via RAG chain (default)
  agentguard-rag-mistral → openrouter-mistral via RAG chain
  agentguard-direct      → openrouter-gemini-flash via LiteLLM directly
                           (no RAG context; useful for guardrail demos)
"""

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langfuse import propagate_attributes
from opentelemetry import trace as otel_trace
from pydantic import BaseModel

from app.config import settings
from app.rag.chain import build_rag_chain
from app.telemetry import get_otel_trace_id, init_telemetry
from app.tracing import get_langfuse_client, get_langfuse_handler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_telemetry(app)
    yield


app = FastAPI(title="AgentGuard RAG API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_MODELS = {
    "agentguard-rag": "openrouter-gemini-flash",
    "agentguard-rag-mistral": "openrouter-mistral",
    "agentguard-direct": "openrouter-gemini-flash",
}

# Models that bypass the RAG chain and call LiteLLM directly.
# PII masking and injection guard still apply (they live in LiteLLM).
_DIRECT_MODELS = {"agentguard-direct"}


# ── Request / response schemas ────────────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "agentguard-rag"
    messages: list[Message]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    # injected by Open WebUI Langfuse Session Linker filter (v0.2+)
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

_HEALTH_TIMEOUT = 5.0


async def _probe(name: str, url: str, headers: dict | None = None) -> tuple[str, dict]:
    try:
        async with httpx.AsyncClient(timeout=_HEALTH_TIMEOUT) as client:
            r = await client.get(url, headers=headers or {})
            r.raise_for_status()
        return name, {"status": "ok"}
    except httpx.TimeoutException:
        return name, {"status": "error", "error": "timeout"}
    except httpx.HTTPStatusError as e:
        return name, {"status": "error", "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return name, {"status": "error", "error": str(e)}


@app.get("/health")
async def health(response: Response):
    results = await asyncio.gather(
        _probe("litellm", f"{settings.litellm_base_url}/health/liveliness",
               {"Authorization": f"Bearer {settings.litellm_master_key}"}),
        _probe("langfuse", f"{settings.langfuse_base_url}/api/public/health"),
        _probe("qdrant", f"{settings.qdrant_url}/healthz"),
    )
    checks = dict(results)
    all_ok = all(v["status"] == "ok" for v in checks.values())
    if not all_ok:
        response.status_code = 503
    return {"status": "ok" if all_ok else "degraded", "checks": checks}


@app.get("/v1/models")
def list_models():
    descriptions = {
        "agentguard-rag": "RAG over Langfuse Academy docs (Gemini Flash)",
        "agentguard-rag-mistral": "RAG over Langfuse Academy docs (Mistral)",
        "agentguard-direct": "Direct LLM — no RAG context, guardrails only",
    }
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "agentguard",
                "description": descriptions.get(model_id, ""),
            }
            for model_id in _MODELS
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(body: ChatRequest, request: Request):
    request_id = uuid.uuid4().hex[:12]

    user_messages = [m for m in body.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    query = user_messages[-1].content
    litellm_model = _MODELS.get(body.model, "openrouter-gemini-flash")

    # Open WebUI sends the chat UUID either in the "chat-id" header (older builds)
    # or via the Langfuse Session Linker filter function which injects it into the
    # request body as chat_id.  Either source stamps it as Langfuse session_id.
    chat_id: Optional[str] = request.headers.get("chat-id") or body.chat_id
    trace_metadata: dict = {"owui_model": body.model}
    if body.message_id:
        trace_metadata["message_id"] = body.message_id
    if body.user_name:
        trace_metadata["user_name"] = body.user_name

    # Annotate the active OTel span with request-level attributes so Jaeger
    # shows model, RAG mode, and session alongside the HTTP trace.
    span = otel_trace.get_current_span()
    span.set_attribute("app.model", body.model)
    span.set_attribute("app.is_rag", body.model not in _DIRECT_MODELS)
    if chat_id:
        span.set_attribute("app.chat_id", chat_id)

    # Cross-link OTel trace into Langfuse metadata so both systems are
    # navigable from the same trace record.
    otel_tid = get_otel_trace_id()
    if otel_tid:
        trace_metadata["otel_trace_id"] = otel_tid

    if body.model in _DIRECT_MODELS:
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
        callbacks = [handler]

        # Always use invoke (non-streaming to LiteLLM) so the post-call PII
        # masking hook sees the complete response before we stream it back.
        chain = build_rag_chain(model=litellm_model)
        try:
            with propagate_attributes(
                session_id=chat_id,
                user_id=body.user_id,
                metadata=trace_metadata,
            ):
                result = chain.invoke(query, config={"callbacks": callbacks})
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
            _stream_from_result(result, completion_id, body.model),
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


# ── Open WebUI feedback webhook ───────────────────────────────────────────────

@app.post("/webhook")
async def webhook(request: Request):
    """Receive Open WebUI thumbs-up/down and push a score to Langfuse.

    Open WebUI sends feedback events to the webhook URL configured in
    Admin Panel → Settings → General → Webhook URL.

    Expected payload (Open WebUI ≥ 0.3):
      {"type": "feedback", "data": {"message_id": "<uuid>", "rating": 1|-1, ...}}
    """
    try:
        payload = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid JSON"}

    logger.info("webhook payload: %s", payload)

    # Extract message_id and rating — tolerate minor format variations.
    data = payload.get("data", payload)
    message_id: Optional[str] = (
        data.get("message_id") or data.get("id") or payload.get("message_id")
    )
    raw_rating = data.get("rating") or data.get("feedback", {}).get("rating")

    if not message_id or raw_rating is None:
        logger.warning("webhook: missing message_id or rating — payload=%s", payload)
        return {"ok": False, "error": "missing message_id or rating"}

    # Map thumbs up (1) → 1.0, thumbs down (-1) → 0.0
    score_value = 1.0 if int(raw_rating) > 0 else 0.0
    comment = data.get("comment") or data.get("feedback", {}).get("comment") or ""

    try:
        get_langfuse_client().create_score(
            trace_id=message_id,
            name="user_feedback",
            value=score_value,
            comment=comment or None,
            data_type="BOOLEAN",
        )
        logger.info("scored trace %s: user_feedback=%.1f", message_id, score_value)
    except Exception as exc:
        logger.error("failed to score trace %s: %s", message_id, exc)
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "trace_id": message_id, "score": score_value}


# ── Streaming helper ──────────────────────────────────────────────────────────

async def _stream_from_result(
    result: str,
    completion_id: str,
    model_name: str,
) -> AsyncGenerator[str, None]:
    """Stream a pre-computed (already PII-masked) result as SSE chunks."""
    yield _sse(completion_id, model_name, {"role": "assistant", "content": ""})
    yield _sse(completion_id, model_name, {"content": result})
    yield _sse(completion_id, model_name, {}, finish_reason="stop")
    yield "data: [DONE]\n\n"


def _sse(
    completion_id: str,
    model: str,
    delta: dict,
    finish_reason: Optional[str] = None,
) -> str:
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload)}\n\n"
