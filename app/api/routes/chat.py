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

    chat_id = request.headers.get("chat-id") or body.chat_id
    result, completion_id = await chat_service.complete(
        body, user_messages[-1].content, chat_id, request_id()
    )

    if body.stream:
        return StreamingResponse(
            stream_from_result(result, completion_id, body.model),
            media_type="text/event-stream",
        )

    return chat_service.build_completion_response(completion_id, body.model, result)
