Given where the project is, here are the most impactful additions grouped by effort:

Low effort, high demo value

[x] Semantic caching in LiteLLM — Add cache: true + a Redis cache config to litellm_config.yaml. Repeated or similar queries return instantly, cost $0, and the cache hit/miss is visible in Langfuse traces. One config block.

[x] Langfuse Prompt Management — Move the RAG_SYSTEM_PROMPT in chain.py out of code and into Langfuse's Prompt Registry. The chain fetches it at runtime via langfuse.get_prompt("rag-system-prompt"). Demonstrates versioning and A/B testing prompts through the UI — a whole Langfuse feature you currently skip entirely.
Medium effort, closes the loop

[x] Human feedback → Langfuse scores — Open WebUI has built-in thumbs up/down on responses. Wire those reactions to push a user_feedback score back to the corresponding Langfuse trace. Completes the feedback loop: real user signal flows into the same scoring system as your automated evaluators.

[ ] Auto-promote traces to dataset — A CLI command (python -m app.main promote-traces --dataset rag-eval-v1 --limit 10) that pulls recent high-quality traces from Langfuse and adds them to a dataset automatically. Currently dataset building requires manual UI clicks — this makes it scriptable.
Bigger but architecturally interesting

[ ] Online evaluation — A background worker that watches Langfuse for new traces and runs your code-based evaluators automatically on every production query, not just in batch eval runs. Shows the "continuous eval" pattern.

[ ] Reranker step — Add a cross-encoder reranker (e.g. cross-encoder/ms-marco-MiniLM) between Qdrant retrieval and LLM generation to re-sort the top-k chunks by relevance. Demonstrable improvement on ambiguous queries, shows the retrieval augmentation can be improved independently of the LLM.

My recommendation: Prompt Management is the highest-ROI pick for a portfolio piece — it's a named Langfuse feature, takes ~30 lines of code, and makes the system prompt editable/versioned from the UI. Semantic caching is a 10-minute win that makes demos snappier. Start there.