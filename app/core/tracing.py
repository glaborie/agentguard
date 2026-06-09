"""Langfuse tracing integration for LangChain."""

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langchain_core.callbacks import BaseCallbackHandler

from app.core.config import settings
from app.core.feature_flags import get_flags

__all__ = ["get_langfuse_client", "get_langfuse_handler"]

_langfuse = Langfuse(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    base_url=settings.langfuse_base_url,
    timeout=60,
)


class _NoopHandler(BaseCallbackHandler):
    """Drop-in replacement when Langfuse tracing is disabled.

    Implements BaseCallbackHandler (all methods no-op by default).
    Provides last_trace_id=None so call sites don't need guarding.
    """

    last_trace_id: str | None = None


def get_langfuse_handler(**kwargs) -> CallbackHandler | _NoopHandler:
    """Return a real Langfuse handler or a no-op stub based on runtime flag."""
    if not get_flags().get("langfuse_tracing_enabled", True):
        return _NoopHandler()
    return CallbackHandler(public_key=settings.langfuse_public_key, **kwargs)


def get_langfuse_client() -> Langfuse:
    return _langfuse
