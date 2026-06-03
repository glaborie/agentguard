"""Semantic cache for LiteLLM proxy using Qdrant (vectors) + Redis (responses).

Registration: listed under litellm_settings.callbacks in litellm_config.yaml.
LiteLLM imports SemanticCacheActivator at startup, which triggers module-level
code that sets litellm.cache = QdrantSemanticCache() in the proxy process.
"""

import asyncio
import json
import logging
import os
from typing import Any, Optional
from uuid import uuid4

import httpx
import redis.asyncio as aioredis
from litellm.caching import BaseCache
from litellm.integrations.custom_logger import CustomLogger
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

logger = logging.getLogger(__name__)

_COLLECTION = os.environ.get("SEMANTIC_CACHE_COLLECTION", "semantic-cache")
_THRESHOLD = float(os.environ.get("SEMANTIC_CACHE_THRESHOLD", "0.85"))
_TTL = int(os.environ.get("SEMANTIC_CACHE_TTL", "3600"))
_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
_QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
_REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
_REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
_REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")
_VECTOR_SIZE = 768  # nomic-embed-text output dimension


def _messages_to_text(messages: list[dict]) -> str:
    """Flatten a messages list to a single string for embedding."""
    return " ".join(
        m.get("content", "")
        for m in messages
        if isinstance(m.get("content"), str)
    )


class QdrantSemanticCache(BaseCache):
    pass
