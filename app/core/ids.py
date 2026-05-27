"""Request and completion ID generators."""

import uuid

__all__ = ["request_id", "completion_id"]


def request_id() -> str:
    """Short random hex ID for correlating log lines within a single request."""
    return uuid.uuid4().hex[:12]


def completion_id() -> str:
    """OpenAI-style completion ID (chatcmpl-<hex8>)."""
    return f"chatcmpl-{uuid.uuid4().hex[:8]}"
