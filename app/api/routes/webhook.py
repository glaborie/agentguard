import logging

from fastapi import APIRouter, Request

from app.api.services import feedback_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/webhook")
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

    message_id, score_value, comment = feedback_service.parse_feedback(payload)
    if message_id is None:
        logger.warning("webhook: missing message_id or rating — payload=%s", payload)
        return {"ok": False, "error": "missing message_id or rating"}

    try:
        feedback_service.push_score(message_id, score_value, comment)
    except Exception as exc:
        logger.error("failed to score trace %s: %s", message_id, exc)
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "trace_id": message_id, "score": score_value}
