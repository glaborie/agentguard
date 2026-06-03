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
    def __init__(self):
        self._qdrant = AsyncQdrantClient(url=_QDRANT_URL)
        self._redis = aioredis.Redis(
            host=_REDIS_HOST,
            port=_REDIS_PORT,
            password=_REDIS_PASSWORD or None,
            decode_responses=True,
        )
        self._http = httpx.AsyncClient(timeout=10.0)
        self._collection_ready = False

    def _serialize(self, value: Any) -> str:
        """Serialize value to JSON string, handling Pydantic models."""
        if hasattr(value, "model_dump"):
            return json.dumps(value.model_dump())
        if hasattr(value, "dict"):
            return json.dumps(value.dict())
        return json.dumps(value, default=str)

    async def _ensure_collection(self) -> None:
        if self._collection_ready:
            return
        collections = await self._qdrant.get_collections()
        names = [c.name for c in collections.collections]
        if _COLLECTION not in names:
            await self._qdrant.create_collection(
                collection_name=_COLLECTION,
                vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
            )
        self._collection_ready = True

    async def _embed(self, text: str) -> list[float]:
        resp = await self._http.post(
            f"{_OLLAMA_URL}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    async def async_get_cache(self, key: str, **kwargs) -> Optional[Any]:
        if os.environ.get("SEMANTIC_CACHE_ENABLED", "true").lower() != "true":
            return None
        try:
            messages = kwargs.get("messages", [])
            if not messages:
                return None
            text = _messages_to_text(messages)
            vector = await self._embed(text)
            await self._ensure_collection()
            results = await self._qdrant.search(
                collection_name=_COLLECTION,
                query_vector=vector,
                limit=1,
                score_threshold=_THRESHOLD,
                with_payload=True,
            )
            if not results:
                return None
            cache_key = results[0].payload.get("cache_key")
            if not cache_key:
                return None
            raw = await self._redis.get(f"semantic_cache:{cache_key}")
            if raw is None:
                return None
            logger.info("semantic_cache: HIT score=%.3f key=%s", results[0].score, cache_key)
            return json.loads(raw)
        except Exception:
            logger.warning("semantic_cache: get_cache error", exc_info=True)
            return None

    async def async_set_cache(self, key: str, value: Any, **kwargs) -> None:
        if os.environ.get("SEMANTIC_CACHE_ENABLED", "true").lower() != "true":
            return
        try:
            messages = kwargs.get("messages", [])
            if not messages:
                return
            text = _messages_to_text(messages)
            vector = await self._embed(text)
            await self._ensure_collection()
            cache_key = str(uuid4())
            await self._qdrant.upsert(
                collection_name=_COLLECTION,
                points=[
                    PointStruct(
                        id=cache_key,
                        vector=vector,
                        payload={"cache_key": cache_key, "model": kwargs.get("model", "")},
                    )
                ],
            )
            await self._redis.setex(
                f"semantic_cache:{cache_key}",
                _TTL,
                self._serialize(value),
            )
            logger.info("semantic_cache: SET key=%s", cache_key)
        except Exception:
            logger.warning("semantic_cache: set_cache error", exc_info=True)

    def get_cache(self, key: str, **kwargs) -> Optional[Any]:
        try:
            return asyncio.run(self.async_get_cache(key, **kwargs))
        except RuntimeError:
            return None
        except Exception:
            return None

    def set_cache(self, key: str, value: Any, **kwargs) -> None:
        try:
            asyncio.run(self.async_set_cache(key, value, **kwargs))
        except RuntimeError:
            pass
        except Exception:
            pass


class SemanticCacheActivator(CustomLogger):
    """Dummy CustomLogger subclass.

    LiteLLM proxy imports this class via litellm_settings.callbacks at startup.
    The import triggers the module-level litellm.cache assignment below,
    registering QdrantSemanticCache within the proxy process.
    """


# Module-level: runs when LiteLLM proxy imports this module at startup.
# Removes need for cache_params in litellm_config.yaml — our assignment
# takes effect before any requests are served.
if os.environ.get("SEMANTIC_CACHE_ENABLED", "true").lower() == "true":
    import litellm as _litellm
    _litellm.cache = QdrantSemanticCache()
