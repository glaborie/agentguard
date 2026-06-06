# Agent → Open WebUI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the LangGraph ReAct agent as `agentguard-agent` model in Open WebUI alongside existing RAG/direct models.

**Architecture:** Add `agentguard-agent` to the models list and a new `agent_llm.py` service that holds a singleton `(graph, MemorySaver)`. `chat_service.complete()` gains one new dispatch branch routing `agentguard-agent` requests to `agent_llm.call()`. `chat_id` maps to LangGraph `thread_id` for stateful multi-turn memory.

**Tech Stack:** LangGraph (`app/agent/graph.py`, `app/agent/service.py`), FastAPI, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/api/services/models_service.py` | Modify | Add `agentguard-agent` model + `AGENT_MODELS` set |
| `app/api/services/agent_llm.py` | Create | Singleton graph+checkpointer; `call()` → `(str, completion_id)` |
| `app/api/services/chat_service.py` | Modify | Route `AGENT_MODELS` to `agent_llm.call()` |
| `tests/test_agent_llm.py` | Create | Unit tests for new service + routing |

---

### Task 1: Add `agentguard-agent` to the model list

**Files:**
- Modify: `app/api/services/models_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_llm.py
from app.api.services.models_service import AGENT_MODELS, MODELS, get_model_list


def test_agent_model_in_models():
    assert "agentguard-agent" in MODELS


def test_agent_models_set():
    assert "agentguard-agent" in AGENT_MODELS


def test_agent_model_in_model_list():
    result = get_model_list()
    ids = [m["id"] for m in result["data"]]
    assert "agentguard-agent" in ids
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_agent_llm.py -v
```

Expected: FAIL — `ImportError: cannot import name 'AGENT_MODELS'`

- [ ] **Step 3: Update `models_service.py`**

```python
import time

MODELS: dict[str, str] = {
    "agentguard-rag": "openrouter-gemini-flash",
    "agentguard-rag-mistral": "openrouter-mistral",
    "agentguard-direct": "openrouter-gemini-flash",
    "agentguard-agent": "openrouter-gemini-flash",
}

DIRECT_MODELS: set[str] = {"agentguard-direct"}
AGENT_MODELS: set[str] = {"agentguard-agent"}

_DESCRIPTIONS: dict[str, str] = {
    "agentguard-rag": "RAG over NorthstarCRM knowledge base (Gemini Flash)",
    "agentguard-rag-mistral": "RAG over NorthstarCRM knowledge base (Mistral)",
    "agentguard-direct": "Direct LLM — no RAG context, guardrails only",
    "agentguard-agent": "ReAct agent with tools — doc search, trace listing, scoring",
}


def get_model_list() -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "agentguard",
                "description": _DESCRIPTIONS.get(model_id, ""),
            }
            for model_id in MODELS
        ],
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_agent_llm.py::test_agent_model_in_models tests/test_agent_llm.py::test_agent_models_set tests/test_agent_llm.py::test_agent_model_in_model_list -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/api/services/models_service.py tests/test_agent_llm.py
git commit -m "feat(agent): add agentguard-agent to model registry"
```

---

### Task 2: Create `agent_llm.py` service

**Files:**
- Create: `app/api/services/agent_llm.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_agent_llm.py`:

```python
from unittest.mock import MagicMock, patch


def test_call_returns_tuple(monkeypatch):
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "messages": [MagicMock(content="agent answer")]
    }

    with patch("app.api.services.agent_llm._get_graph", return_value=mock_graph):
        from app.api.services import agent_llm
        result, cid = agent_llm.call(
            query="hello",
            chat_id="chat-abc",
            user_id=None,
            request_id="req-001",
        )

    assert result == "agent answer"
    assert cid.startswith("chatcmpl-")


def test_call_uses_chat_id_as_thread_id(monkeypatch):
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "messages": [MagicMock(content="ok")]
    }

    with patch("app.api.services.agent_llm._get_graph", return_value=mock_graph):
        from app.api.services import agent_llm
        agent_llm.call(
            query="hello",
            chat_id="my-chat-id",
            user_id=None,
            request_id="req-002",
        )

    call_kwargs = mock_graph.invoke.call_args
    config = call_kwargs[1]["config"] if "config" in call_kwargs[1] else call_kwargs[0][1]
    assert config["configurable"]["thread_id"] == "my-chat-id"


def test_call_falls_back_to_request_id_when_no_chat_id(monkeypatch):
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "messages": [MagicMock(content="ok")]
    }

    with patch("app.api.services.agent_llm._get_graph", return_value=mock_graph):
        from app.api.services import agent_llm
        agent_llm.call(
            query="hello",
            chat_id=None,
            user_id=None,
            request_id="req-fallback",
        )

    call_kwargs = mock_graph.invoke.call_args
    config = call_kwargs[1]["config"] if "config" in call_kwargs[1] else call_kwargs[0][1]
    assert config["configurable"]["thread_id"] == "req-fallback"


def test_call_returns_error_string_on_exception(monkeypatch):
    mock_graph = MagicMock()
    mock_graph.invoke.side_effect = RuntimeError("boom")

    with patch("app.api.services.agent_llm._get_graph", return_value=mock_graph):
        from app.api.services import agent_llm
        result, cid = agent_llm.call(
            query="hello",
            chat_id="chat-err",
            user_id=None,
            request_id="req-err",
        )

    assert "[Error:" in result
    assert cid.startswith("chatcmpl-")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_agent_llm.py -v -k "test_call"
```

Expected: FAIL — `ImportError: cannot import name 'agent_llm'`

- [ ] **Step 3: Create `app/api/services/agent_llm.py`**

```python
import logging
from typing import Optional

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph import build_agent
from app.core.ids import completion_id

logger = logging.getLogger(__name__)

_graph = None
_checkpointer = None


def _get_graph():
    global _graph, _checkpointer
    if _graph is None:
        _checkpointer = MemorySaver()
        _graph = build_agent(checkpointer=_checkpointer)
    return _graph


def call(
    query: str,
    chat_id: Optional[str],
    user_id: Optional[str],
    request_id: str,
) -> tuple[str, str]:
    """Invoke the ReAct agent for one turn. Returns (answer_text, completion_id)."""
    thread_id = chat_id or request_id
    graph = _get_graph()
    config: dict = {"configurable": {"thread_id": thread_id}}

    try:
        result = graph.invoke({"messages": [HumanMessage(content=query)]}, config=config)
        answer = result["messages"][-1].content
    except Exception as e:
        logger.error("[%s] Agent error: %s", request_id, e)
        answer = f"[Error: {e}] (request_id={request_id})"

    return answer, completion_id()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_agent_llm.py -v -k "test_call"
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/api/services/agent_llm.py tests/test_agent_llm.py
git commit -m "feat(agent): add agent_llm service with singleton graph and session routing"
```

---

### Task 3: Route `agentguard-agent` in `chat_service.py`

**Files:**
- Modify: `app/api/services/chat_service.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_agent_llm.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest

from app.api.schemas import ChatRequest, Message


@pytest.mark.asyncio
async def test_chat_service_routes_agent_model():
    body = ChatRequest(
        model="agentguard-agent",
        messages=[Message(role="user", content="what tools do you have?")],
    )

    with patch("app.api.services.agent_llm.call", return_value=("tool answer", "chatcmpl-xyz")) as mock_call:
        from app.api.services import chat_service
        result, cid = await chat_service.complete(
            body=body,
            query="what tools do you have?",
            chat_id="chat-123",
            request_id="req-999",
        )

    mock_call.assert_called_once_with(
        query="what tools do you have?",
        chat_id="chat-123",
        user_id=None,
        request_id="req-999",
    )
    assert result == "tool answer"
    assert cid == "chatcmpl-xyz"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_agent_llm.py::test_chat_service_routes_agent_model -v
```

Expected: FAIL — agent path not yet wired; call routes to RAG instead

- [ ] **Step 3: Update `chat_service.py`**

```python
import time

from opentelemetry import trace as otel_trace

from app.api.schemas import ChatRequest
from app.api.services import agent_llm, direct_llm, rag_llm
from app.api.services.models_service import AGENT_MODELS, DIRECT_MODELS, MODELS
from app.core.telemetry import get_otel_trace_id


def build_trace_metadata(body: ChatRequest, otel_tid: str | None) -> dict[str, str]:
    metadata: dict[str, str] = {"owui_model": body.model}
    if body.message_id:
        metadata["message_id"] = body.message_id
    if body.user_name:
        metadata["user_name"] = body.user_name
    if otel_tid:
        metadata["otel_trace_id"] = otel_tid
    return metadata


def annotate_span(body: ChatRequest, chat_id: str | None) -> None:
    """Set OTel span attributes so Jaeger shows model, RAG mode, and session."""
    span = otel_trace.get_current_span()
    span.set_attribute("app.model", body.model)
    span.set_attribute("app.is_rag", body.model not in DIRECT_MODELS and body.model not in AGENT_MODELS)
    if chat_id:
        span.set_attribute("app.chat_id", chat_id)


async def complete(
    body: ChatRequest,
    query: str,
    chat_id: str | None,
    request_id: str,
) -> tuple[str, str]:
    """Orchestrate direct, RAG, or agent completion. Returns (result_text, completion_id)."""
    litellm_model = MODELS.get(body.model, "openrouter-gemini-flash")
    trace_metadata = build_trace_metadata(body, get_otel_trace_id())
    annotate_span(body, chat_id)

    if body.model in AGENT_MODELS:
        return await agent_llm.call(
            query=query,
            chat_id=chat_id,
            user_id=body.user_id,
            request_id=request_id,
        )

    if body.model in DIRECT_MODELS:
        return await direct_llm.call(
            [m.model_dump() for m in body.messages],
            litellm_model,
            request_id,
            query=query,
            chat_id=chat_id,
            user_id=body.user_id,
        )

    return await rag_llm.call(
        query,
        litellm_model,
        chat_id,
        body.user_id,
        trace_metadata,
        request_id,
    )


def build_completion_response(completion_id: str, model: str, result: str) -> dict[str, object]:
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
```

Note: `agent_llm.call()` is synchronous but `complete()` is `async`. Wrap the blocking call with `asyncio.to_thread` to avoid blocking the event loop:

Update the agent branch in `complete()`:

```python
import asyncio

    if body.model in AGENT_MODELS:
        return await asyncio.to_thread(
            agent_llm.call,
            query=query,
            chat_id=chat_id,
            user_id=body.user_id,
            request_id=request_id,
        )
```

And update `agent_llm.py` signature accordingly — `call()` stays synchronous (LangGraph `invoke` is sync).

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_agent_llm.py -v
```

Expected: all tests PASSED

- [ ] **Step 5: Run full unit suite to check for regressions**

```bash
pytest -m "not integration" -v
```

Expected: all existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add app/api/services/chat_service.py
git commit -m "feat(agent): route agentguard-agent model to agent_llm in chat_service"
```

---

### Task 4: Final wiring verification

- [ ] **Step 1: Start the FastAPI server (host)**

```bash
uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

- [ ] **Step 2: Verify model appears in list**

```bash
curl -s http://localhost:8000/v1/models | python -m json.tool | grep agentguard-agent
```

Expected output includes:
```
"id": "agentguard-agent",
```

- [ ] **Step 3: Send a test message**

```bash
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "chat-id: test-session-001" \
  -d '{"model":"agentguard-agent","messages":[{"role":"user","content":"What tools do you have?"}]}' \
  | python -m json.tool
```

Expected: JSON response with `choices[0].message.content` containing agent answer about its tools.

- [ ] **Step 4: Verify session continuity**

Send a follow-up with same `chat-id`:

```bash
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "chat-id: test-session-001" \
  -d '{"model":"agentguard-agent","messages":[{"role":"user","content":"What did I just ask you?"}]}' \
  | python -m json.tool
```

Expected: agent references "What tools do you have?" from memory.

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "feat(agent): wire ReAct agent into Open WebUI via agentguard-agent model"
```
