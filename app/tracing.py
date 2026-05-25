"""Langfuse tracing integration for LangChain."""

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from app.config import settings

_langfuse = Langfuse(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    base_url=settings.langfuse_base_url,
)


def get_langfuse_handler(**kwargs) -> CallbackHandler:
    return CallbackHandler(public_key=settings.langfuse_public_key, **kwargs)


def get_langfuse_client() -> Langfuse:
    return _langfuse
