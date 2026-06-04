"""Push guardrail events as Langfuse scores so they appear in the dashboard."""

import logging
import re
import uuid
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_AUTH = None


def _auth() -> str:
    global _AUTH
    if _AUTH is None:
        import base64
        raw = f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}"
        _AUTH = base64.b64encode(raw.encode()).decode()
    return _AUTH


def _lf_headers() -> dict:
    return {"Authorization": f"Basic {_auth()}", "Content-Type": "application/json"}


# Matches error messages raised by custom_guardrails.py
_GUARDRAIL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"semantic injection", re.IGNORECASE), "prompt_injection_semantic"),
    (re.compile(r"prompt injection", re.IGNORECASE), "prompt_injection"),
    (re.compile(r"toxic", re.IGNORECASE), "toxicity"),
]

# PII redaction tokens written by PIIMaskingGuard
_PII_TOKEN_RE = re.compile(r"\[(EMAIL|SSN|CARD|PHONE)_REDACTED\]", re.IGNORECASE)


def detect_guardrail_type(error_detail: object) -> Optional[str]:
    """Return a guardrail type label from a LiteLLM 400 error detail, or None."""
    text = str(error_detail)
    for pattern, label in _GUARDRAIL_PATTERNS:
        if pattern.search(text):
            return label
    return None


def _post_score(trace_id: str, name: str, value: float, comment: Optional[str] = None) -> None:
    payload: dict = {
        "traceId": trace_id,
        "name": name,
        "value": value,
        "dataType": "BOOLEAN",
    }
    if comment:
        payload["comment"] = comment
    try:
        resp = httpx.post(
            f"{settings.langfuse_base_url}/api/public/scores",
            json=payload,
            headers=_lf_headers(),
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("guardrail_scoring: score POST failed (%s): %s", name, exc)


def _create_trace(
    query: str,
    guardrail_type: str,
    *,
    chat_id: Optional[str],
    user_id: Optional[str],
) -> str:
    """POST a minimal trace to Langfuse ingestion API. Returns the trace ID."""
    trace_id = str(uuid.uuid4())
    body: dict = {
        "batch": [
            {
                "type": "trace-create",
                "id": str(uuid.uuid4()),
                "body": {
                    "id": trace_id,
                    "name": "guardrail_block",
                    "input": query,
                    "output": "[blocked]",
                    "tags": [guardrail_type, "guardrail"],
                    **({"sessionId": chat_id} if chat_id else {}),
                    **({"userId": user_id} if user_id else {}),
                },
            }
        ]
    }
    try:
        resp = httpx.post(
            f"{settings.langfuse_base_url}/api/public/ingestion",
            json=body,
            headers=_lf_headers(),
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("guardrail_scoring: trace create failed: %s", exc)
    return trace_id


def score_guardrail_block(
    guardrail_type: str,
    query: str,
    trace_id: Optional[str],
    *,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    """Record a guardrail block as Langfuse scores.

    If trace_id is None (direct path — no LangChain trace was created), a
    minimal trace is created via the ingestion API so scores have a home.
    """
    try:
        if not trace_id:
            trace_id = _create_trace(query, guardrail_type, chat_id=chat_id, user_id=user_id)
        _post_score(trace_id, f"guardrail_{guardrail_type}", 1.0, f"blocked by {guardrail_type}")
        _post_score(trace_id, "guardrail_triggered", 1.0, guardrail_type)
    except Exception as exc:
        logger.warning("guardrail_scoring: score_guardrail_block failed: %s", exc)


def score_pii_masked(trace_id: str, response_text: str) -> None:
    """Add a pii_masked score if response contains redaction tokens."""
    if not _PII_TOKEN_RE.search(response_text):
        return
    _post_score(trace_id, "guardrail_pii_masked", 1.0, "PII redacted in response")
