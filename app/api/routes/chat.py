import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest
from app.api.services import chat_service
from app.api.streaming import stream_from_result
from app.core.ids import request_id

router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(body: ChatRequest, request: Request):
    user_messages = [m for m in body.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    chat_id: Optional[str] = request.headers.get("chat-id") or body.chat_id
    req_id = request_id()

    result, completion_id = await chat_service.complete(
        body, user_messages[-1].content, chat_id, req_id
    )

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
