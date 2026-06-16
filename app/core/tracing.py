"""Langfuse and Opik tracing integration for LangChain."""

import os

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langchain_core.callbacks import BaseCallbackHandler
from opik.integrations.langchain import OpikTracer

from app.core.config import settings
from app.core.feature_flags import get_flags

__all__ = ["get_langfuse_client", "get_langfuse_handler", "get_opik_handler", "get_callbacks"]

_langfuse = Langfuse(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    base_url=settings.langfuse_base_url,
    timeout=settings.http_timeout_seconds,
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


def get_opik_handler(project_name: str | None = None) -> OpikTracer | _NoopHandler:
    """Return an Opik LangChain tracer or a no-op stub when disabled."""
    if not settings.opik_tracing_enabled:
        return _NoopHandler()
    os.environ.setdefault("OPIK_URL_OVERRIDE", settings.opik_url_override)
    os.environ.setdefault("OPIK_PROJECT_NAME", settings.opik_project_name)
    os.environ.setdefault("OPIK_WORKSPACE", settings.opik_workspace)
    return OpikTracer(project_name=project_name or settings.opik_project_name)


def get_callbacks(**langfuse_kwargs) -> list[BaseCallbackHandler]:
    """Return all active tracing callbacks for a LangChain invocation."""
    return [get_langfuse_handler(**langfuse_kwargs), get_opik_handler()]


def get_langfuse_client() -> Langfuse:
    return _langfuse
