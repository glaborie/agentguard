import logging
from typing import Optional

from fastapi import APIRouter, Request

from app.tracing import get_langfuse_client

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

    data = payload.get("data", payload)
    message_id: Optional[str] = (
        data.get("message_id") or data.get("id") or payload.get("message_id")
    )
    raw_rating = data.get("rating") or data.get("feedback", {}).get("rating")

    if not message_id or raw_rating is None:
        logger.warning("webhook: missing message_id or rating — payload=%s", payload)
        return {"ok": False, "error": "missing message_id or rating"}

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
