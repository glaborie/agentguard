from fastapi import APIRouter, Request

from app.api.services import feedback_service

router = APIRouter()


@router.post("/webhook")
async def webhook(request: Request):
    """Receive Open WebUI thumbs-up/down and push a score to Langfuse."""
    try:
        payload = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid JSON"}
    return feedback_service.handle_webhook(payload)
