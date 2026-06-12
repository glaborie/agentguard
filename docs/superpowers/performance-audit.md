Yes — the biggest potential performance issues are around **synchronous network fan-out, repeated expensive LLM/eval calls, and cache implementation overhead**.

Also, note: the code-search tools only return a limited set of matches, so this is **likely incomplete**. To inspect more in GitHub UI, use:
- Semantic/code search UI: https://github.com/search?q=repo%3Aglaborie%2Fagentguard+performance&type=code
- Lexical search UI: https://github.com/search?q=repo%3Aglaborie%2Fagentguard+cache+OR+async+OR+await+OR+perf+OR+performance&type=code

## CTO / PM take: top risks by business impact

### 1. Benchmarking is likely slow and expensive because it runs serially
In `app/eval/benchmark.py`, `run_benchmark()` loops item-by-item and mode-by-mode, and each path appears to call either the RAG pipeline or the LLM directly.

Evidence:
- `run_benchmark()` iterates sequentially over `items` and `modes`
- `_run_direct()` does a blocking `httpx.post(... timeout=60)`

This creates a classic throughput bottleneck:
- total time grows roughly with `items × modes × remote-call-latency`
- if `llm_judge=True`, cost and latency likely increase materially again

Relevant references:
```python name=app/eval/benchmark.py url=https://github.com/glaborie/agentguard/blob/a190863394c66c10d4071f83540df52b457df724/app/eval/benchmark.py#L362-L400
def run_benchmark(
    items: dict[str, BenchmarkItem],
    retrieval_labels: dict[str, list[str]],
    modes: list[RunMode],
    model: str | None = None,
    llm_judge: bool = True,
    limit: int | None = None,
    verbose: bool = False,
) -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []
    items_list = list(items.values())
    if limit:
        items_list = items_list[:limit]

    for item in items_list:
        gold_docs = retrieval_labels.get(item.id, item.gold_docs)
        for mode in modes:
            ...
            if mode == "full":
                answer, sources = _run_rag(question=item.question, guardrails_enabled=True, model=model)
            elif mode == "no-guardrails":
                answer, sources = _run_rag(question=item.question, guardrails_enabled=False, model=model)
            else:
                answer, sources = _run_direct(question=item.question, model=model)
```

```python name=app/eval/benchmark.py url=https://github.com/glaborie/agentguard/blob/a190863394c66c10d4071f83540df52b457df724/app/eval/benchmark.py#L328-L348
def _run_direct(question: str, model: str | None = None) -> tuple[str, list[str]]:
    import httpx

    resp = httpx.post(
        f"{settings.litellm_base_url}/v1/chat/completions",
        json={
            "model": model or settings.default_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful sales assistant for NorthstarCRM.",
                },
                {"role": "user", "content": question},
            ],
        },
        headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        timeout=60,
    )
```

**Why this matters:** benchmark and eval tooling becomes painful to run, so teams run it less often. That undermines product quality and release confidence.

**Recommendation:** move benchmark execution to bounded concurrency (`asyncio` + semaphore / worker pool), especially for remote inference calls.

---

### 2. Semantic cache may add noticeable latency on every request
The semantic cache design is good strategically, but the implementation may be too heavy for hot-path usage.

In `guardrails/semantic_cache.py`, every cache set appears to:
1. transform messages to text
2. call embedding model
3. ensure Qdrant collection
4. upsert into Qdrant
5. write serialized payload to Redis

Relevant reference:
```python name=guardrails/semantic_cache.py url=https://github.com/glaborie/agentguard/blob/a190863394c66c10d4071f83540df52b457df724/guardrails/semantic_cache.py#L119-L163
async def async_set_cache(self, key: str = "", value: Any = None, **kwargs) -> None:
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
```

Potential issues:
- **Embedding on every cache write** can be expensive.
- **`_ensure_collection()` on every write** suggests repeated control-plane work in the hot path.
- Storing by generated UUID rather than deterministic key means cache growth may be high and dedupe may be weak.
- Depending on `async_get_cache`, semantic lookup likely also requires an embedding call on reads, which can erase some latency benefit for short requests.

The design doc itself confirms this architecture:
```markdown name=docs/superpowers/specs/2026-06-03-semantic-cache-design.md url=https://github.com/glaborie/agentguard/blob/a190863394c66c10d4071f83540df52b457df724/docs/superpowers/specs/2026-06-03-semantic-cache-design.md#L7-L31
LiteLLM receives request
    │
    ▼
QdrantSemanticCache.async_get_cache(key, **kwargs)
    │
    ├─ embed messages → nomic-embed-text (Ollama :11434)
    ├─ Qdrant search collection "semantic-cache", top-1, threshold 0.85
    │   ├─ HIT  → fetch response from Redis by UUID key → return to caller
    │   └─ MISS → return None → LiteLLM proceeds to LLM
```

**Why this matters:** if cache lookup itself is expensive, you risk making p50 worse in order to improve p95/p99 on repeats.

**Recommendation:** 
- initialize/ensure collection once at startup
- add a cheap exact-hash cache tier before semantic cache
- cache embeddings for recent prompts
- consider async fire-and-forget writes or batch writes for set path

---

### 3. Async/sync boundary may be causing hidden overhead or cache misses
`get_cache()` and `set_cache()` wrap async methods using `asyncio.run(...)`, then suppress runtime errors.

Relevant reference:
```python name=guardrails/semantic_cache.py url=https://github.com/glaborie/agentguard/blob/a190863394c66c10d4071f83540df52b457df724/guardrails/semantic_cache.py#L143-L159
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
```

Potential consequences:
- `asyncio.run()` is expensive if invoked repeatedly.
- In an already-running event loop, it throws `RuntimeError`, and this code returns `None` / no-op.
- That means in some runtime contexts the cache may silently not work, which becomes a **performance bug disguised as resilience**.

**Why this matters:** you may think semantic cache is protecting cost/latency, but in production it could be disabled by execution context.

**Recommendation:** expose fully async usage in the hot path, or use loop-aware scheduling instead of `asyncio.run()`.

---

### 4. Red-team execution is also serial and network-bound
`scripts/red_team.py` generates variants, then probes each variant sequentially.

Relevant reference:
```python name=scripts/red_team.py url=https://github.com/glaborie/agentguard/blob/a190863394c66c10d4071f83540df52b457df724/scripts/red_team.py#L230-L246
for i, variant in enumerate(variants, 1):
    result = _probe_variant(
        variant=variant,
        attack_type=attack_type,
        proxy_url=effective_proxy,
        master_key=effective_key,
        model=effective_model,
        timeout=timeout,
    )
    all_probes.append(result)
```

This is fine for tiny runs, but scales poorly for:
- CI safety gates
- scheduled red-team suites
- enterprise demo workloads

**Recommendation:** parallelize probe execution with bounded concurrency and collect aggregate failures at the end.

---

### 5. Health checks create a fresh HTTP client per probe
In `app/api/services/health_service.py`, `_probe()` creates a new `httpx.AsyncClient()` for each service probe.

Relevant reference:
```python name=app/api/services/health_service.py url=https://github.com/glaborie/agentguard/blob/a190863394c66c10d4071f83540df52b457df724/app/api/services/health_service.py#L8-L19
async def _probe(
    name: str, url: str, headers: dict[str, str] | None = None
) -> tuple[str, dict[str, str]]:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(url, headers=headers or {})
            r.raise_for_status()
```

This is not the top issue, but it is suboptimal:
- repeated connection setup
- no connection pooling reuse
- avoidable overhead if health is polled frequently by orchestrators

**Recommendation:** reuse a shared client or inject one.

---

### 6. Trace indexing may become expensive at scale
`scripts/sync_feedback.py` paginates through Langfuse traces until a fetch limit.

Relevant reference:
```python name=scripts/sync_feedback.py url=https://github.com/glaborie/agentguard/blob/a190863394c66c10d4071f83540df52b457df724/scripts/sync_feedback.py#L127-L148
def _build_trace_index(lf: Langfuse) -> tuple[dict[str, str], dict[str, list[tuple[str, int]]]]:
    ...
    while fetched < TRACE_FETCH_LIMIT:
        try:
            resp = lf.api.trace.list(name="RunnableSequence", limit=TRACE_PAGE_SIZE, page=page)
            traces = resp.data if hasattr(resp, "data") else []
```

Potential issue:
- repeated full-ish scans of recent traces
- possible O(n) rebuild behavior instead of incremental indexing
- memory growth with `by_question` buckets

**Why this matters:** background jobs often start “fine” and become operationally expensive as production traces grow.

**Recommendation:** move to incremental sync using last-seen cursor/timestamp and avoid rebuilding indexes from scratch.

---

## Secondary concerns

### 7. Repeated LLM-as-judge calls can dominate evaluation cost
`app/eval/evaluators.py` imports `ChatOpenAI`, and benchmark docs indicate LLM-as-judge metrics are part of the flow.

That means the benchmark likely triggers:
- one model call to generate an answer
- plus additional model calls to judge answer quality/safety/helpfulness

This compounds both:
- runtime
- infra spend

As a PM/CTO, I’d treat this as a **productiveness tax** unless aggressively sampled or parallelized.

---

### 8. Worker polling architecture may create idle overhead
`scripts/worker.py` shows loop-based worker behavior. Combined with the notes in `PLAN.md` about poll intervals, this suggests periodic polling rather than event-driven processing.

That usually causes:
- unnecessary wakeups
- slower freshness than webhooks/events
- bursty backend load

---

## Prioritized remediation roadmap

### High ROI, low complexity
1. **Parallelize benchmark and red-team execution**
2. **Remove `asyncio.run()` from cache hot paths**
3. **Ensure semantic cache collection once, not per operation**
4. **Add an exact-match cache before semantic cache**

### Medium-term
5. **Convert feedback sync to incremental/cursor-based processing**
6. **Reuse HTTP clients in health and service integrations**
7. **Sample or batch LLM-as-judge evaluations**

### Strategic
8. **Instrument latency breakdowns per request**
   - retrieval latency
   - embedding latency
   - Qdrant latency
   - LiteLLM latency
   - guardrail latency
   - cache hit ratio / lookup cost

Without that observability, optimization effort will be guesswork.

---

## My CTO summary
If I were prioritizing this for a product roadmap, I would say:

- **Most likely real bottleneck today:** serial evaluation/red-team workflows
- **Most likely hidden production bottleneck:** semantic cache overhead and async/sync misuse
- **Most important architectural risk:** expensive “reliability” features on the request path without latency budgets

If you want, I can do a **deeper performance audit** next and rank findings by:
1. **request-path latency**,  
2. **background-job scalability**, and  
3. **cloud cost impact**.
