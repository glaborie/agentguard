"""Unit tests for QdrantSemanticCache.

All litellm, qdrant_client, and redis imports are mocked so these tests
run on the host without Docker.
"""

import asyncio
import json
import os
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ── Mock litellm module hierarchy ─────────────────────────────────

_mock_litellm = ModuleType("litellm")
_mock_litellm.cache = None  # will be set by semantic_cache module-level code

class _FakeModelResponse(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.__dict__.update(kwargs)

_mock_litellm.ModelResponse = _FakeModelResponse

_mock_caching = ModuleType("litellm.caching")

class _FakeBaseCache:
    pass

_mock_caching.BaseCache = _FakeBaseCache

_mock_integrations = ModuleType("litellm.integrations")
_mock_custom_logger = ModuleType("litellm.integrations.custom_logger")

class _FakeCustomLogger:
    def __init__(self, **kwargs):
        pass

_mock_custom_logger.CustomLogger = _FakeCustomLogger
_mock_integrations.custom_logger = _mock_custom_logger

sys.modules["litellm"] = _mock_litellm
sys.modules["litellm.caching"] = _mock_caching
sys.modules["litellm.integrations"] = _mock_integrations
sys.modules["litellm.integrations.custom_logger"] = _mock_custom_logger

# ── Mock qdrant_client ────────────────────────────────────────────

_mock_qdrant_pkg = ModuleType("qdrant_client")
_mock_qdrant_models = ModuleType("qdrant_client.models")

class _FakeAsyncQdrantClient:
    def __init__(self, *args, **kwargs):
        pass

class _FakePointStruct:
    def __init__(self, id, vector, payload):
        self.id = id
        self.vector = vector
        self.payload = payload

class _FakeVectorParams:
    def __init__(self, size, distance):
        self.size = size
        self.distance = distance

class _FakeDistance:
    COSINE = "Cosine"

_mock_qdrant_pkg.AsyncQdrantClient = _FakeAsyncQdrantClient
_mock_qdrant_models.PointStruct = _FakePointStruct
_mock_qdrant_models.VectorParams = _FakeVectorParams
_mock_qdrant_models.Distance = _FakeDistance

sys.modules["qdrant_client"] = _mock_qdrant_pkg
sys.modules["qdrant_client.models"] = _mock_qdrant_models

# ── Mock redis.asyncio ────────────────────────────────────────────

_mock_redis_pkg = ModuleType("redis")
_mock_redis_asyncio = ModuleType("redis.asyncio")

class _FakeRedis:
    def __init__(self, *args, **kwargs):
        pass

_mock_redis_asyncio.Redis = _FakeRedis
_mock_redis_pkg.asyncio = _mock_redis_asyncio

sys.modules["redis"] = _mock_redis_pkg
sys.modules["redis.asyncio"] = _mock_redis_asyncio

# ── Now import the module under test ─────────────────────────────

import os
os.environ["SEMANTIC_CACHE_ENABLED"] = "true"
os.environ["SEMANTIC_CACHE_THRESHOLD"] = "0.85"
os.environ["SEMANTIC_CACHE_COLLECTION"] = "semantic-cache"
os.environ["SEMANTIC_CACHE_TTL"] = "3600"
os.environ["OLLAMA_URL"] = "http://ollama:11434"
os.environ["QDRANT_URL"] = "http://qdrant:6333"
os.environ["REDIS_HOST"] = "redis"
os.environ["REDIS_PORT"] = "6379"
os.environ["REDIS_PASSWORD"] = "testpass"

from guardrails.semantic_cache import QdrantSemanticCache, _messages_to_text


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def cache():
    return QdrantSemanticCache()

SAMPLE_MESSAGES = [
    {"role": "user", "content": "What is the refund policy?"}
]
SAMPLE_VECTOR = [0.1] * 768
SAMPLE_RESPONSE = {"choices": [{"message": {"content": "30-day returns."}}]}


# ── Test Classes ──────────────────────────────────────────────────

class TestMessagesToText:
    def test_single_user_message(self):
        msgs = [{"role": "user", "content": "Hello world"}]
        assert _messages_to_text(msgs) == "Hello world"

    def test_multi_turn(self):
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Bye"},
        ]
        result = _messages_to_text(msgs)
        assert "You are helpful." in result
        assert "Hi" in result
        assert "Bye" in result

    def test_skips_non_string_content(self):
        msgs = [{"role": "user", "content": None}, {"role": "user", "content": "real"}]
        assert _messages_to_text(msgs) == "real"

    def test_empty_messages(self):
        assert _messages_to_text([]) == ""


class TestAsyncGetCacheMiss:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_messages(self, cache):
        result = await cache.async_get_cache("key123", messages=[])
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_tools_present(self, cache):
        tools = [{"type": "function", "function": {"name": "search_docs"}}]
        result = await cache.async_get_cache("key123", messages=SAMPLE_MESSAGES, tools=tools)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_qdrant_empty_results(self, cache):
        with patch.object(cache, "_embed", return_value=SAMPLE_VECTOR), \
             patch.object(cache, "_ensure_collection", return_value=None):
            mock_qdrant = AsyncMock()
            mock_qdrant.search = AsyncMock(return_value=[])
            cache._qdrant = mock_qdrant
            result = await cache.async_get_cache("key123", messages=SAMPLE_MESSAGES)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_redis_key_missing(self, cache):
        mock_hit = SimpleNamespace(score=0.91, payload={"cache_key": "abc-123"})
        with patch.object(cache, "_embed", return_value=SAMPLE_VECTOR), \
             patch.object(cache, "_ensure_collection", return_value=None):
            mock_qdrant = AsyncMock()
            mock_qdrant.search = AsyncMock(return_value=[mock_hit])
            cache._qdrant = mock_qdrant
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=None)
            cache._redis = mock_redis
            result = await cache.async_get_cache("key123", messages=SAMPLE_MESSAGES)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_disabled(self, cache):
        with patch.dict(os.environ, {"SEMANTIC_CACHE_ENABLED": "false"}):
            result = await cache.async_get_cache("key123", messages=SAMPLE_MESSAGES)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_embed_failure(self, cache):
        with patch.object(cache, "_embed", side_effect=httpx.ConnectError("down")):
            result = await cache.async_get_cache("key123", messages=SAMPLE_MESSAGES)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_qdrant_failure(self, cache):
        with patch.object(cache, "_embed", return_value=SAMPLE_VECTOR), \
             patch.object(cache, "_ensure_collection", return_value=None):
            mock_qdrant = AsyncMock()
            mock_qdrant.search = AsyncMock(side_effect=Exception("qdrant down"))
            cache._qdrant = mock_qdrant
            result = await cache.async_get_cache("key123", messages=SAMPLE_MESSAGES)
        assert result is None


class TestAsyncGetCacheHit:
    @pytest.mark.asyncio
    async def test_returns_cached_response_on_hit(self, cache):
        mock_hit = SimpleNamespace(score=0.92, payload={"cache_key": "abc-123"})
        serialized = json.dumps(SAMPLE_RESPONSE)
        mock_result = SimpleNamespace(points=[mock_hit])

        with patch.object(cache, "_embed", return_value=SAMPLE_VECTOR), \
             patch.object(cache, "_ensure_collection", return_value=None):
            mock_qdrant = AsyncMock()
            mock_qdrant.query_points = AsyncMock(return_value=mock_result)
            cache._qdrant = mock_qdrant

            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=serialized)
            cache._redis = mock_redis

            result = await cache.async_get_cache("key123", messages=SAMPLE_MESSAGES)

        import litellm
        assert isinstance(result, litellm.ModelResponse)
        assert result["choices"] == SAMPLE_RESPONSE["choices"]

    @pytest.mark.asyncio
    async def test_score_below_threshold_is_miss(self, cache):
        # Qdrant score_threshold filters server-side; empty results = below threshold
        mock_result = SimpleNamespace(points=[])
        with patch.object(cache, "_embed", return_value=SAMPLE_VECTOR), \
             patch.object(cache, "_ensure_collection", return_value=None):
            mock_qdrant = AsyncMock()
            mock_qdrant.query_points = AsyncMock(return_value=mock_result)
            cache._qdrant = mock_qdrant
            result = await cache.async_get_cache("key123", messages=SAMPLE_MESSAGES)

        assert result is None


class TestAsyncSetCache:
    @pytest.mark.asyncio
    async def test_upserts_to_qdrant_and_writes_redis(self, cache):
        with patch.object(cache, "_embed", return_value=SAMPLE_VECTOR), \
             patch.object(cache, "_ensure_collection", return_value=None):
            mock_qdrant = AsyncMock()
            mock_qdrant.upsert = AsyncMock()
            cache._qdrant = mock_qdrant

            mock_redis = AsyncMock()
            mock_redis.setex = AsyncMock()
            cache._redis = mock_redis

            await cache.async_set_cache(
                "key123", SAMPLE_RESPONSE, messages=SAMPLE_MESSAGES, model="gemini-flash"
            )

        mock_qdrant.upsert.assert_called_once()
        call_kwargs = mock_qdrant.upsert.call_args
        assert call_kwargs.kwargs["collection_name"] == "semantic-cache"
        points = call_kwargs.kwargs["points"]
        assert len(points) == 1
        assert points[0].vector == SAMPLE_VECTOR
        assert "cache_key" in points[0].payload
        assert points[0].payload["model"] == "gemini-flash"

        mock_redis.setex.assert_called_once()
        setex_args = mock_redis.setex.call_args[0]
        assert setex_args[0].startswith("semantic_cache:")
        assert setex_args[1] == 3600
        assert json.loads(setex_args[2]) == SAMPLE_RESPONSE

    @pytest.mark.asyncio
    async def test_skips_when_no_messages(self, cache):
        with patch.object(cache, "_embed", return_value=SAMPLE_VECTOR):
            mock_qdrant = AsyncMock()
            cache._qdrant = mock_qdrant
            await cache.async_set_cache("key123", SAMPLE_RESPONSE, messages=[])
        mock_qdrant.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_tools_present(self, cache):
        tools = [{"type": "function", "function": {"name": "search_docs"}}]
        with patch.object(cache, "_embed", return_value=SAMPLE_VECTOR):
            mock_qdrant = AsyncMock()
            cache._qdrant = mock_qdrant
            await cache.async_set_cache("key123", SAMPLE_RESPONSE, messages=SAMPLE_MESSAGES, tools=tools)
        mock_qdrant.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_silently_handles_qdrant_error(self, cache):
        with patch.object(cache, "_embed", return_value=SAMPLE_VECTOR), \
             patch.object(cache, "_ensure_collection", return_value=None):
            mock_qdrant = AsyncMock()
            mock_qdrant.upsert = AsyncMock(side_effect=Exception("qdrant down"))
            cache._qdrant = mock_qdrant
            # Must not raise
            await cache.async_set_cache("key123", SAMPLE_RESPONSE, messages=SAMPLE_MESSAGES)

    @pytest.mark.asyncio
    async def test_disabled_skips_write(self, cache):
        with patch.dict(os.environ, {"SEMANTIC_CACHE_ENABLED": "false"}):
            with patch.object(cache, "_embed") as mock_embed:
                await cache.async_set_cache("key123", SAMPLE_RESPONSE, messages=SAMPLE_MESSAGES)
            mock_embed.assert_not_called()


class TestSemanticCacheActivator:
    def test_litellm_cache_set_when_enabled(self):
        import litellm
        assert isinstance(litellm.cache, QdrantSemanticCache)

    def test_activator_is_custom_logger_subclass(self):
        from guardrails.semantic_cache import SemanticCacheActivator
        from litellm.integrations.custom_logger import CustomLogger
        assert issubclass(SemanticCacheActivator, CustomLogger)
