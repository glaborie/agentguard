# Semantic Cache — Design Spec
**Date:** 2026-06-03
**Branch:** feat/output-schema-validation
**Status:** Approved

## Goal

Add semantic caching to the LiteLLM proxy so that semantically similar queries return cached LLM responses, reducing cost and latency. Uses Qdrant for vector similarity lookup and Redis for response storage.

## Architecture

```
LiteLLM receives request
    │
    ▼
QdrantSemanticCache.async_get_cache(key, **kwargs)
    │
    ├─ embed messages → nomic-embed-text (Ollama :11434)
    ├─ Qdrant search collection "semantic-cache", top-1, threshold 0.85
    │   ├─ HIT  → fetch response from Redis by UUID key → return to caller
    │   └─ MISS → return None → LiteLLM proceeds to LLM
    │
    ▼ (on LLM response)
QdrantSemanticCache.async_set_cache(key, value, **kwargs)
    ├─ embed messages → nomic-embed-text
    ├─ upsert vector + {uuid, model, timestamp} payload into Qdrant
    └─ SET uuid → serialized response in Redis (TTL 3600s)
```

## Components

### New file: `guardrails/semantic_cache.py`

- Class `QdrantSemanticCache(BaseCache)` from `litellm.caching`
- Implements `get_cache`, `set_cache`, `async_get_cache`, `async_set_cache`
- Embedding: HTTP POST to `{OLLAMA_URL}/api/embeddings` with `nomic-embed-text`
- Qdrant: `qdrant_client.AsyncQdrantClient` — collection `semantic-cache`, cosine distance, 768-dim
- Redis: `redis.asyncio.Redis` — key = UUID, value = JSON-serialized LLM response, TTL = `SEMANTIC_CACHE_TTL`
- Mounted into LiteLLM container alongside `custom_guardrails.py`

### Qdrant collection: `semantic-cache`

- Vector size: 768 (nomic-embed-text output dim)
- Distance: Cosine
- Payload per point: `{"cache_key": "<uuid>", "model": "<model_name>", "created_at": "<iso_timestamp>"}`
- Collection auto-created on first cache write if not exists

### Redis keys

- Pattern: `semantic_cache:<uuid>`
- Value: JSON string of the LLM response object
- TTL: `SEMANTIC_CACHE_TTL` seconds (default 3600)

## Error Contract

Any failure (Qdrant unreachable, embed call fails, Redis miss) returns `None`. LiteLLM falls through to the real LLM call. The cache is never on the critical path. All errors logged at WARNING level.

## Configuration

### `litellm_config.yaml`

```yaml
litellm_settings:
  cache: true
  cache_params:
    type: "custom"
    custom_cache_class: "semantic_cache.QdrantSemanticCache"
    host: "redis"
    port: 6379
    password: "os.environ/REDIS_PASSWORD"
    ttl: 3600
```

### New env vars (`.env.example` + LiteLLM service in `docker-compose.yml`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `SEMANTIC_CACHE_ENABLED` | `true` | Master switch |
| `SEMANTIC_CACHE_THRESHOLD` | `0.85` | Cosine similarity minimum for cache hit |
| `SEMANTIC_CACHE_COLLECTION` | `semantic-cache` | Qdrant collection name |
| `SEMANTIC_CACHE_TTL` | `3600` | Redis key TTL in seconds |

Existing vars reused: `QDRANT_URL`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `OLLAMA_URL` (via `http://ollama:11434`).

### `docker-compose.yml` — LiteLLM service

- Add volume mount: `./guardrails/semantic_cache.py:/app/semantic_cache.py`
- Add env vars: `SEMANTIC_CACHE_ENABLED`, `SEMANTIC_CACHE_THRESHOLD`, `SEMANTIC_CACHE_COLLECTION`, `SEMANTIC_CACHE_TTL`

## Data Flow Detail

### Cache read (`async_get_cache`)

1. Extract `messages` list from `kwargs`
2. Concatenate message content into single string for embedding
3. POST to Ollama `/api/embeddings` → 768-dim float vector
4. `qdrant.search(collection="semantic-cache", query_vector=vector, limit=1, score_threshold=0.85)`
5. If result: extract `cache_key` from payload → `redis.get(f"semantic_cache:{cache_key}")`
6. If Redis value exists: deserialize JSON → return LLM response object
7. Else: return `None`

### Cache write (`async_set_cache`)

1. Extract `messages` from `kwargs`, `value` = LLM response
2. Embed messages (same as read path)
3. `cache_key = str(uuid4())`
4. `qdrant.upsert(collection="semantic-cache", points=[PointStruct(id=uuid, vector=vector, payload={...})])`
5. `redis.setex(f"semantic_cache:{cache_key}", ttl, json.dumps(value))`

## Testing

### Unit tests: `tests/test_semantic_cache.py`

- Mock `httpx.AsyncClient` for Ollama embed calls
- Mock `AsyncQdrantClient` for search/upsert
- Mock `redis.asyncio.Redis` for get/setex
- Test: cache miss → returns `None`
- Test: cache hit → returns deserialized response
- Test: Qdrant down → returns `None` (no exception)
- Test: embed fails → returns `None` (no exception)
- Test: score below threshold → returns `None`

### Integration test: `tests/test_integration.py` (new class)

- Send same query twice → assert second response time significantly lower
- Send paraphrased query → assert cache hit (score ≥ 0.85)
- Verify Qdrant collection `semantic-cache` has one point after first query
- Verify Redis key exists with correct TTL

## Files Changed

| File | Change |
|------|--------|
| `guardrails/semantic_cache.py` | New — cache implementation |
| `litellm_config.yaml` | Update `cache_params.type` and `custom_cache_class` |
| `docker-compose.yml` | Mount + env vars for LiteLLM service |
| `.env.example` | Add 4 new env vars |
| `tests/test_semantic_cache.py` | New — unit tests |
| `tests/test_integration.py` | Add semantic cache integration test class |
