"""Unit tests for QdrantSemanticCache.

All litellm, qdrant_client, and redis imports are mocked so these tests
run on the host without Docker.
"""

import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Mock litellm module hierarchy ─────────────────────────────────

_mock_litellm = ModuleType("litellm")
_mock_litellm.cache = None  # will be set by semantic_cache module-level code

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
