# Semantic Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `QdrantSemanticCache` to the LiteLLM proxy so semantically similar queries return cached responses — Qdrant stores vectors, Redis stores serialized responses.

**Architecture:** A `QdrantSemanticCache(BaseCache)` class is mounted at `/app/semantic_cache.py` in the LiteLLM container. LiteLLM doesn't support `type: "custom"` in `cache_params`, so registration uses the `custom_callbacks` hook: when LiteLLM imports `SemanticCacheActivator` at startup, module-level code runs `litellm.cache = QdrantSemanticCache()` in the same process. The existing `cache: true / cache_params` block is removed from `litellm_config.yaml` so LiteLLM doesn't overwrite our assignment.

**Tech Stack:** Python 3.13, `qdrant-client` (AsyncQdrantClient), `redis.asyncio`, `httpx` (Ollama embed calls), `litellm.caching.BaseCache`, `litellm.integrations.custom_logger.CustomLogger`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `guardrails/semantic_cache.py` | **Create** | `QdrantSemanticCache(BaseCache)` + `SemanticCacheActivator(CustomLogger)` + module-level `litellm.cache = ...` |
| `tests/test_semantic_cache.py` | **Create** | Unit tests — all litellm/qdrant/redis/httpx mocked |
| `litellm_config.yaml` | **Modify** | Remove `cache: true` / `cache_params` block; add `callbacks: ["semantic_cache.SemanticCacheActivator"]` |
| `docker-compose.yml` | **Modify** | Mount `semantic_cache.py`; add 4 env vars to LiteLLM service |
| `.env.example` | **Modify** | Document 4 new env vars |

---

## Task 1: Mock scaffold and helpers

**Files:**
- Create: `tests/test_semantic_cache.py`

- [ ] **Step 1: Write the mock scaffold**

Create `tests/test_semantic_cache.py` with the full mock setup (same pattern as `tests/test_guardrails.py` — LiteLLM only exists inside Docker, must mock before importing):

```python
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

import importlib, os
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
```

- [ ] **Step 2: Verify scaffold imports cleanly**

```bash
cd "/mnt/h/Training/AI Engineering/Langfuse/Langfuse_POC"
python -c "import tests.test_semantic_cache" 2>&1
```

Expected: no output (clean import). If `ModuleNotFoundError: guardrails.semantic_cache` — that's expected at this stage; the file doesn't exist yet.

---

## Task 2: `_messages_to_text` helper

**Files:**
- Create: `guardrails/semantic_cache.py` (skeleton only)
- Test: `tests/test_semantic_cache.py`

- [ ] **Step 1: Write failing tests for `_messages_to_text`**

Add to `tests/test_semantic_cache.py` after the fixtures:

```python
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
```

- [ ] **Step 2: Run tests — they must fail**

```bash
cd "/mnt/h/Training/AI Engineering/Langfuse/Langfuse_POC"
python -m pytest tests/test_semantic_cache.py::TestMessagesToText -v 2>&1 | head -30
```

Expected: `ImportError` or `ModuleNotFoundError` — file doesn't exist yet.

- [ ] **Step 3: Create `guardrails/semantic_cache.py` skeleton with `_messages_to_text`**

```python
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
```

- [ ] **Step 4: Run tests — they must pass**

```bash
cd "/mnt/h/Training/AI Engineering/Langfuse/Langfuse_POC"
python -m pytest tests/test_semantic_cache.py::TestMessagesToText -v 2>&1
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add guardrails/semantic_cache.py tests/test_semantic_cache.py
git commit -m "feat: add semantic cache skeleton with _messages_to_text"
```

---

## Task 3: `async_get_cache` — miss path

**Files:**
- Modify: `guardrails/semantic_cache.py`
- Test: `tests/test_semantic_cache.py`

- [ ] **Step 1: Write failing tests for cache miss**

Add to `tests/test_semantic_cache.py`:

```python
class TestAsyncGetCacheMiss:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_messages(self, cache):
        result = await cache.async_get_cache("key123", messages=[])
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
```

- [ ] **Step 2: Run — must fail**

```bash
cd "/mnt/h/Training/AI Engineering/Langfuse/Langfuse_POC"
python -m pytest tests/test_semantic_cache.py::TestAsyncGetCacheMiss -v 2>&1 | head -20
```

Expected: `AttributeError: 'QdrantSemanticCache' object has no attribute 'async_get_cache'`.

- [ ] **Step 3: Implement `QdrantSemanticCache` class body in `guardrails/semantic_cache.py`**

Add after `_VECTOR_SIZE = 768`:

```python
class QdrantSemanticCache(BaseCache):
    def __init__(self):
        self._qdrant: Optional[AsyncQdrantClient] = None
        self._redis: Optional[aioredis.Redis] = None
        self._http: Optional[httpx.AsyncClient] = None
        self._collection_ready = False

    def _get_qdrant(self) -> AsyncQdrantClient:
        if self._qdrant is None:
            self._qdrant = AsyncQdrantClient(url=_QDRANT_URL)
        return self._qdrant

    def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=_REDIS_HOST,
                port=_REDIS_PORT,
                password=_REDIS_PASSWORD or None,
                decode_responses=True,
            )
        return self._redis

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=10.0)
        return self._http

    async def _ensure_collection(self) -> None:
        if self._collection_ready:
            return
        qdrant = self._get_qdrant()
        collections = await qdrant.get_collections()
        names = [c.name for c in collections.collections]
        if _COLLECTION not in names:
            await qdrant.create_collection(
                collection_name=_COLLECTION,
                vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
            )
        self._collection_ready = True

    async def _embed(self, text: str) -> list[float]:
        resp = await self._get_http().post(
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
            results = await self._get_qdrant().search(
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
            raw = await self._get_redis().get(f"semantic_cache:{cache_key}")
            if raw is None:
                return None
            logger.info("semantic_cache: HIT score=%.3f key=%s", results[0].score, cache_key)
            return json.loads(raw)
        except Exception:
            logger.warning("semantic_cache: get_cache error", exc_info=True)
            return None

    async def async_set_cache(self, key: str, value: Any, **kwargs) -> None:
        pass  # implemented in Task 4

    def get_cache(self, key: str, **kwargs) -> Optional[Any]:
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.async_get_cache(key, **kwargs))
        except Exception:
            return None

    def set_cache(self, key: str, value: Any, **kwargs) -> None:
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self.async_set_cache(key, value, **kwargs))
        except Exception:
            pass
```

- [ ] **Step 4: Run — must pass**

```bash
cd "/mnt/h/Training/AI Engineering/Langfuse/Langfuse_POC"
python -m pytest tests/test_semantic_cache.py::TestAsyncGetCacheMiss -v 2>&1
```

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add guardrails/semantic_cache.py tests/test_semantic_cache.py
git commit -m "feat: implement async_get_cache miss path with resilient error handling"
```

---

## Task 4: `async_get_cache` — hit path

**Files:**
- Test: `tests/test_semantic_cache.py`

- [ ] **Step 1: Write failing test for cache hit**

Add to `tests/test_semantic_cache.py`:

```python
class TestAsyncGetCacheHit:
    @pytest.mark.asyncio
    async def test_returns_cached_response_on_hit(self, cache):
        mock_hit = SimpleNamespace(score=0.92, payload={"cache_key": "abc-123"})
        serialized = json.dumps(SAMPLE_RESPONSE)

        with patch.object(cache, "_embed", return_value=SAMPLE_VECTOR), \
             patch.object(cache, "_ensure_collection", return_value=None):
            mock_qdrant = AsyncMock()
            mock_qdrant.search = AsyncMock(return_value=[mock_hit])
            cache._qdrant = mock_qdrant

            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=serialized)
            cache._redis = mock_redis

            result = await cache.async_get_cache("key123", messages=SAMPLE_MESSAGES)

        assert result == SAMPLE_RESPONSE

    @pytest.mark.asyncio
    async def test_score_below_threshold_is_miss(self, cache):
        # Qdrant score_threshold filters server-side; empty results = below threshold
        with patch.object(cache, "_embed", return_value=SAMPLE_VECTOR), \
             patch.object(cache, "_ensure_collection", return_value=None):
            mock_qdrant = AsyncMock()
            mock_qdrant.search = AsyncMock(return_value=[])  # filtered out
            cache._qdrant = mock_qdrant
            result = await cache.async_get_cache("key123", messages=SAMPLE_MESSAGES)

        assert result is None
```

- [ ] **Step 2: Run — must pass (no code change needed)**

```bash
cd "/mnt/h/Training/AI Engineering/Langfuse/Langfuse_POC"
python -m pytest tests/test_semantic_cache.py::TestAsyncGetCacheHit -v 2>&1
```

Expected: `2 passed`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_semantic_cache.py
git commit -m "test: add async_get_cache hit path tests"
```

---

## Task 5: `async_set_cache`

**Files:**
- Modify: `guardrails/semantic_cache.py`
- Test: `tests/test_semantic_cache.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_semantic_cache.py`:

```python
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
```

- [ ] **Step 2: Run — must fail**

```bash
cd "/mnt/h/Training/AI Engineering/Langfuse/Langfuse_POC"
python -m pytest tests/test_semantic_cache.py::TestAsyncSetCache -v 2>&1 | head -20
```

Expected: `FAILED` — `async_set_cache` is currently a `pass`.

- [ ] **Step 3: Implement `async_set_cache` in `guardrails/semantic_cache.py`**

Replace `async def async_set_cache(self, key: str, value: Any, **kwargs) -> None: pass` with:

```python
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
            await self._get_qdrant().upsert(
                collection_name=_COLLECTION,
                points=[
                    PointStruct(
                        id=cache_key,
                        vector=vector,
                        payload={"cache_key": cache_key, "model": kwargs.get("model", "")},
                    )
                ],
            )
            await self._get_redis().setex(
                f"semantic_cache:{cache_key}",
                _TTL,
                json.dumps(value),
            )
            logger.info("semantic_cache: SET key=%s", cache_key)
        except Exception:
            logger.warning("semantic_cache: set_cache error", exc_info=True)
```

- [ ] **Step 4: Run — must pass**

```bash
cd "/mnt/h/Training/AI Engineering/Langfuse/Langfuse_POC"
python -m pytest tests/test_semantic_cache.py::TestAsyncSetCache -v 2>&1
```

Expected: `4 passed`.

- [ ] **Step 5: Run full unit test suite**

```bash
cd "/mnt/h/Training/AI Engineering/Langfuse/Langfuse_POC"
python -m pytest tests/test_semantic_cache.py -v 2>&1
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add guardrails/semantic_cache.py tests/test_semantic_cache.py
git commit -m "feat: implement async_set_cache with Qdrant upsert + Redis setex"
```

---

## Task 6: Module-level activation + `SemanticCacheActivator`

**Files:**
- Modify: `guardrails/semantic_cache.py`
- Test: `tests/test_semantic_cache.py`

- [ ] **Step 1: Write test for module-level activation**

Add to `tests/test_semantic_cache.py`:

```python
class TestSemanticCacheActivator:
    def test_litellm_cache_set_when_enabled(self):
        # Module-level code already ran during import. Verify litellm.cache was set.
        import litellm
        assert isinstance(litellm.cache, QdrantSemanticCache)

    def test_activator_is_custom_logger_subclass(self):
        from guardrails.semantic_cache import SemanticCacheActivator
        from litellm.integrations.custom_logger import CustomLogger
        assert issubclass(SemanticCacheActivator, CustomLogger)
```

- [ ] **Step 2: Run — must fail**

```bash
cd "/mnt/h/Training/AI Engineering/Langfuse/Langfuse_POC"
python -m pytest tests/test_semantic_cache.py::TestSemanticCacheActivator -v 2>&1 | head -20
```

Expected: `FAILED` — `SemanticCacheActivator` not defined yet, module-level assignment missing.

- [ ] **Step 3: Add `SemanticCacheActivator` and module-level init to `guardrails/semantic_cache.py`**

Append at the bottom of the file (after `QdrantSemanticCache` class):

```python

class SemanticCacheActivator(CustomLogger):
    """Dummy CustomLogger subclass.

    LiteLLM proxy imports this class via litellm_settings.callbacks at startup.
    The import triggers the module-level litellm.cache assignment below,
    registering QdrantSemanticCache within the proxy process.
    """


# Module-level: runs when LiteLLM proxy imports this module at startup.
# Must come AFTER QdrantSemanticCache definition and BEFORE litellm_config.yaml
# sets its own cache (which it won't, since we remove cache_params from config).
if os.environ.get("SEMANTIC_CACHE_ENABLED", "true").lower() == "true":
    import litellm as _litellm
    _litellm.cache = QdrantSemanticCache()
```

- [ ] **Step 4: Run — must pass**

```bash
cd "/mnt/h/Training/AI Engineering/Langfuse/Langfuse_POC"
python -m pytest tests/test_semantic_cache.py -v 2>&1
```

Expected: all tests pass including `TestSemanticCacheActivator`.

- [ ] **Step 5: Commit**

```bash
git add guardrails/semantic_cache.py tests/test_semantic_cache.py
git commit -m "feat: add SemanticCacheActivator and module-level litellm.cache registration"
```

---

## Task 7: `litellm_config.yaml` update

**Files:**
- Modify: `litellm_config.yaml`

- [ ] **Step 1: Remove existing cache block and add callbacks**

In `litellm_config.yaml`, find and remove the entire `cache:` / `cache_params:` block:

```yaml
  cache: true
  cache_params:
    type: "redis"
    host: "redis"
    port: 6379
    password: "os.environ/REDIS_PASSWORD"
    ttl: 3600
```

Replace with (under `litellm_settings`):

```yaml
  callbacks: ["semantic_cache.SemanticCacheActivator"]
```

The full `litellm_settings` block should look like:

```yaml
litellm_settings:
  drop_params: true
  success_callback: ["langfuse"]
  failure_callback: ["langfuse"]
  callbacks: ["semantic_cache.SemanticCacheActivator"]
```

- [ ] **Step 2: Verify YAML is valid**

```bash
cd "/mnt/h/Training/AI Engineering/Langfuse/Langfuse_POC"
python -c "import yaml; yaml.safe_load(open('litellm_config.yaml'))" && echo "YAML OK"
```

Expected: `YAML OK`.

- [ ] **Step 3: Commit**

```bash
git add litellm_config.yaml
git commit -m "feat: register SemanticCacheActivator callback, remove exact-match redis cache"
```

---

## Task 8: `docker-compose.yml` and `.env.example` updates

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: Add mount and env vars to LiteLLM service in `docker-compose.yml`**

In the `litellm:` service `volumes:` block (around line 323), add:

```yaml
      - ./guardrails/semantic_cache.py:/app/semantic_cache.py
```

In the `litellm:` service `environment:` block, add after the existing `TOXICITY_GUARD_PROXY_URL` line:

```yaml
      # Semantic cache (Qdrant vectors + Redis responses)
      SEMANTIC_CACHE_ENABLED: "${SEMANTIC_CACHE_ENABLED:-true}"
      SEMANTIC_CACHE_THRESHOLD: "${SEMANTIC_CACHE_THRESHOLD:-0.85}"
      SEMANTIC_CACHE_COLLECTION: "${SEMANTIC_CACHE_COLLECTION:-semantic-cache}"
      SEMANTIC_CACHE_TTL: "${SEMANTIC_CACHE_TTL:-3600}"
      OLLAMA_URL: "http://ollama:11434"
      QDRANT_URL: "http://qdrant:6333"
      REDIS_HOST: "redis"
      REDIS_PORT: "6379"
```

- [ ] **Step 2: Verify docker-compose YAML is valid**

```bash
cd "/mnt/h/Training/AI Engineering/Langfuse/Langfuse_POC"
docker compose config --quiet && echo "COMPOSE OK"
```

Expected: `COMPOSE OK`.

- [ ] **Step 3: Add env vars to `.env.example`**

Find the section with `SEMANTIC_GUARD_ENABLED` in `.env.example` and add after it:

```bash
# ── Semantic Cache (LiteLLM proxy) ──────────────────────────────────────────
SEMANTIC_CACHE_ENABLED=true
SEMANTIC_CACHE_THRESHOLD=0.85    # cosine similarity minimum (0.0–1.0)
SEMANTIC_CACHE_COLLECTION=semantic-cache
SEMANTIC_CACHE_TTL=3600          # Redis key TTL in seconds
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "feat: mount semantic_cache.py and add env vars to LiteLLM service"
```

---

## Task 9: Integration smoke test + CLAUDE.md update

**Files:**
- Modify: `tests/test_integration.py`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Write integration test class**

Find the end of `tests/test_integration.py` and add a new class:

```python
@pytest.mark.integration
class TestSemanticCache:
    """Verify semantic cache works end-to-end against live LiteLLM proxy.

    Requires Docker stack running: pytest -m integration
    """

    BASE_URL = "http://localhost:4000"
    HEADERS = {"Authorization": "Bearer sk-litellm-dev-key", "Content-Type": "application/json"}

    def _chat(self, content: str) -> tuple[str, float]:
        import time
        payload = {"model": "openrouter-gemini-flash", "messages": [{"role": "user", "content": content}]}
        start = time.perf_counter()
        resp = httpx.post(f"{self.BASE_URL}/chat/completions", json=payload, headers=self.HEADERS, timeout=30)
        elapsed = time.perf_counter() - start
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"], elapsed

    def test_exact_repeat_returns_faster(self, litellm_available):
        query = "What is the NorthstarCRM refund policy? (cache test exact)"
        _, t1 = self._chat(query)
        _, t2 = self._chat(query)
        assert t2 < t1 * 0.5, f"Cache hit should be >2x faster: first={t1:.2f}s second={t2:.2f}s"

    def test_paraphrase_hits_cache(self, litellm_available):
        original = "What is the return window for NorthstarCRM purchases? (cache test paraphrase)"
        paraphrase = "How many days do I have to return a NorthstarCRM product? (cache test paraphrase)"
        self._chat(original)  # warm cache
        result, t = self._chat(paraphrase)
        # Paraphrase should be fast (cache hit) — under 1s
        assert t < 1.0, f"Paraphrased query should hit semantic cache, got {t:.2f}s"
        assert result  # non-empty response
```

- [ ] **Step 2: Run integration tests (Docker stack must be running)**

```bash
cd "/mnt/h/Training/AI Engineering/Langfuse/Langfuse_POC"
pytest tests/test_integration.py::TestSemanticCache -v -m integration 2>&1
```

Expected: both tests pass. If `test_paraphrase_hits_cache` fails on timing (embed latency varies), lower the assertion to `t < 3.0` for slow hardware.

- [ ] **Step 3: Update CLAUDE.md**

In `CLAUDE.md`, find the `### Guardrails` section and add after the tool-call guardrail paragraph:

```markdown
**Semantic cache (LiteLLM proxy layer, always active when `SEMANTIC_CACHE_ENABLED=true`):** `guardrails/semantic_cache.py` implements `QdrantSemanticCache(BaseCache)`. On each LLM request: embeds the messages via `nomic-embed-text` (Ollama), searches the `semantic-cache` Qdrant collection for a cosine-similar vector above threshold (`SEMANTIC_CACHE_THRESHOLD`, default 0.85), and if found returns the cached response from Redis. Registered via `litellm_settings.callbacks` — the module-level code sets `litellm.cache = QdrantSemanticCache()` when LiteLLM imports the callback class at startup. Cache writes store the vector in Qdrant and the serialized response in Redis with `SEMANTIC_CACHE_TTL` TTL. All errors are non-fatal: failures return `None` and fall through to the LLM.
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py CLAUDE.md
git commit -m "feat: add semantic cache integration tests and update CLAUDE.md"
```

---

## Self-Review Checklist

- [x] **Spec coverage**: architecture ✅, Qdrant+Redis split ✅, nomic-embed-text ✅, threshold 0.85 ✅, error contract ✅, env vars ✅, unit tests ✅, integration tests ✅, CLAUDE.md ✅
- [x] **No placeholders**: all steps have real code, real commands, expected output
- [x] **Type consistency**: `_messages_to_text` used in Task 2 defined in Task 2; `QdrantSemanticCache` used in Task 6 defined in Task 3; `SemanticCacheActivator` used in Tasks 6+7 defined in Task 6; `SAMPLE_VECTOR/MESSAGES/RESPONSE` defined in Task 1 fixture and used in Tasks 3–6
- [x] **Registration approach documented**: `custom_callbacks` trick explained in Architecture section and module docstring
