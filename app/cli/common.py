"""Shared helpers used by CLI commands."""

from app.tracing import get_langfuse_client, get_langfuse_handler


def flush() -> None:
    """Flush buffered Langfuse spans before the process exits."""
    get_langfuse_client().flush()
