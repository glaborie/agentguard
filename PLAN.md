Given where the project is, here are the most impactful additions grouped by effort:

Low effort, high demo value

[x] Semantic caching in LiteLLM — Add cache: true + a Redis cache config to litellm_config.yaml. Repeated or similar queries return instantly, cost $0, and the cache hit/miss is visible in Langfuse traces. One config block.

[x] Langfuse Prompt Management — Move the RAG_SYSTEM_PROMPT in chain.py out of code and into Langfuse's Prompt Registry. The chain fetches it at runtime via langfuse.get_prompt("rag-system-prompt"). Demonstrates versioning and A/B testing prompts through the UI — a whole Langfuse feature you currently skip entirely.
Medium effort, closes the loop

[x] Human feedback → Langfuse scores — Open WebUI has built-in thumbs up/down on responses. Wire those reactions to push a user_feedback score back to the corresponding Langfuse trace. Completes the feedback loop: real user signal flows into the same scoring system as your automated evaluators.

[ ] Auto-promote traces to dataset — A CLI command (python -m app.main promote-traces --dataset rag-eval-v1 --limit 10) that pulls recent high-quality traces from Langfuse and adds them to a dataset automatically. Currently dataset building requires manual UI clicks — this makes it scriptable.
Bigger but architecturally interesting

[x] Online evaluation — A background worker that watches Langfuse for new traces and runs your code-based evaluators automatically on every production query, not just in batch eval runs. Shows the "continuous eval" pattern.

[ ] Reranker step — Add a cross-encoder reranker (e.g. cross-encoder/ms-marco-MiniLM) between Qdrant retrieval and LLM generation to re-sort the top-k chunks by relevance. Demonstrable improvement on ambiguous queries, shows the retrieval augmentation can be improved independently of the LLM.

My recommendation: Prompt Management is the highest-ROI pick for a portfolio piece — it's a named Langfuse feature, takes ~30 lines of code, and makes the system prompt editable/versioned from the UI. Semantic caching is a 10-minute win that makes demos snappier. Start there.

---

Technical debt

High priority

[x] Hardcoded credentials — app/config.py:30-31 has email + password for Open WebUI hardcoded. Move to env vars.
[x] Duplicated HTTP auth header — Basic auth pre-computation copy-pasted in scripts/sync_feedback.py:45 and scripts/online_eval_worker.py:38. Extract shared utility.
[x] Magic numbers — Pagination limits (100, 50, 200), timeouts (60s), poll intervals (120s, 300s) scattered inline. Consolidate as named constants or config.
[x] Fragile state file loading — build_dataset, sync_feedback, online_eval all crash the worker on corrupt JSON state. Add try/except with reset-on-corrupt.

Medium priority

[x] Overly broad exception handling — build_dataset.py:118, sync_feedback.py:258, api.py:136 catch bare Exception and swallow errors silently.
[x] /health always returns 200 — app/api.py health check doesn't probe Qdrant, Langfuse, or LiteLLM. Add real dependency checks.
[x] Fragile timestamp parsing — scripts/sync_feedback.py:149 has redundant datetime reimport inside except block; clean up.

Low priority

[x] Missing type hints on app/main.py CLI functions.
[x] No request IDs in error responses from app/api.py.
[x] Duplicated output-extraction/truncation logic between scripts/online_eval_worker.py and app/agent/tools.py.