import logging

from app.core.tracing import get_langfuse_client

logger = logging.getLogger(__name__)


def parse_feedback(payload: dict) -> tuple[str | None, float | None, str]:
    """Extract (message_id, score_value, comment) from a webhook payload.

    Returns (None, None, "") when the payload is missing required fields.
    Handles both flat payloads and the nested {"data": {...}} shape Open WebUI sends.
    """
    data = payload.get("data", payload)
    message_id: str | None = (
        data.get("message_id") or data.get("id") or payload.get("message_id")
    )
    raw_rating = data.get("rating") or data.get("feedback", {}).get("rating")

    if not message_id or raw_rating is None:
        return None, None, ""

    score_value = 1.0 if int(raw_rating) > 0 else 0.0
    comment: str = data.get("comment") or data.get("feedback", {}).get("comment") or ""
    return message_id, score_value, comment


def push_score(message_id: str, score_value: float, comment: str) -> None:
    """Create a user_feedback score on the Langfuse trace. Raises on error."""
    get_langfuse_client().create_score(
        trace_id=message_id,
        name="user_feedback",
        value=score_value,
        comment=comment or None,
        data_type="BOOLEAN",
    )
    logger.info("scored trace %s: user_feedback=%.1f", message_id, score_value)
