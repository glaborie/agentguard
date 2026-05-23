"""OpenAI-compatible FastAPI wrapper around the RAG chain.

Exposes /v1/models and /v1/chat/completions so Open WebUI (or any
OpenAI-compatible client) can use the RAG pipeline without knowing about
Qdrant or embeddings.  Two virtual models are exposed:

  agentguard-rag         → openrouter-gemini-flash (default)
  agentguard-rag-mistral → openrouter-mistral
"""

import json
import time
import uuid
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.rag.chain import build_rag_chain
from app.tracing import get_langfuse_handler

app = FastAPI(title="AgentGuard RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_MODELS = {
    "agentguard-rag": "openrouter-gemini-flash",
    "agentguard-rag-mistral": "openrouter-mistral",
}


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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "agentguard",
            }
            for model_id in _MODELS
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    user_messages = [m for m in request.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    query = user_messages[-1].content
    litellm_model = _MODELS.get(request.model, "openrouter-gemini-flash")
    callbacks = [get_langfuse_handler()]
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

    # Always use invoke (non-streaming to LiteLLM) so the post-call PII masking
    # hook sees the complete response. The masked result is then streamed to the
    # client in SSE format if requested.
    chain = build_rag_chain(model=litellm_model)
    try:
        result = chain.invoke(query, config={"callbacks": callbacks})
    except Exception as e:
        result = f"[Error: {e}]"

    if request.stream:
        return StreamingResponse(
            _stream_from_result(result, completion_id, request.model),
            media_type="text/event-stream",
        )

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


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
