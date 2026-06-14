"""PII redaction for app-layer masking (before Langfuse callback captures prompts)."""

import re

_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL_REDACTED]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN_REDACTED]"),
    (re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"), "[CARD_REDACTED]"),
    (re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"), "[PHONE_REDACTED]"),
]


def mask(text: str) -> str:
    from app.core.feature_flags import get_flags
    if not get_flags().get("pii_masking_enabled", True):
        return text
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text
