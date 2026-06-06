# Design: Wire app/agent into Open WebUI

**Date:** 2026-06-06
**Branch:** feat/semantic-cache

## Goal

Expose the LangGraph ReAct agent (`app/agent`) as a selectable model in Open WebUI, alongside the existing RAG and direct models. Users pick `agentguard-agent` in the model dropdown and get multi-turn, tool-augmented responses.

## Architecture

No new routes. The existing `/v1/chat/completions` handler already extracts `chat_id` and calls `chat_service.complete()`. We add one branch to that dispatch.

```
Open WebUI → POST /v1/chat/completions (chat-id header)
  → app/api/routes/chat.py          [no change]
  → chat_service.complete()          [add AGENT_MODELS branch]
  → app/api/services/agent_llm.py   [new]
  → app/agent/service.respond()     [existing, unchanged]
```

## Files Changed

| File | Change |
|------|--------|
| `app/api/services/models_service.py` | Add `agentguard-agent` to `MODELS`; add `AGENT_MODELS` set |
| `app/api/services/agent_llm.py` | New file — singleton graph+checkpointer, `call()` function |
| `app/api/services/chat_service.py` | Import `AGENT_MODELS`; add dispatch branch |
| `app/api/routes/chat.py` | No change |

## Session Management

`agent_llm.py` holds two module-level singletons initialized lazily on first call:

```python
_graph = None        # compiled LangGraph (built once)
_checkpointer = None # MemorySaver (holds all threads)
```

`thread_id = chat_id or request_id` — the Open WebUI `chat-id` header maps directly to the LangGraph thread, preserving multi-turn memory within a conversation. Langfuse `session_id = chat_id` (same convention as the RAG path).

**Constraints (acceptable for POC):**
- `MemorySaver` is in-process RAM — restarts lose history
- No thread eviction — threads accumulate until restart

## Return Contract

`agent_llm.call(query, chat_id, user_id, request_id) -> tuple[str, str]`

Returns `(answer_text, completion_id)` — identical shape to `rag_llm.call()` and `direct_llm.call()`. `chat_service.build_completion_response()` is reused unchanged.

## Error Handling

Agent exceptions caught in `agent_llm.call()` and returned as inline error strings — same pattern as `direct_llm.py`. Langfuse and OTel failures remain non-fatal.

## Testing

Unit tests in `tests/test_agent_llm.py`:
- `agentguard-agent` appears in `/v1/models` list
- `chat_service.complete()` routes to `agent_llm.call()` for `agentguard-agent`
- Same `chat_id` produces same `thread_id` across calls (session continuity)
- Missing `chat_id` falls back to `request_id` without error
