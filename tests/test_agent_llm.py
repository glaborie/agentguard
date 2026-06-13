from unittest.mock import Mock, patch

import pytest

from app.api.services.models_service import AGENT_MODELS, MODELS, get_model_list


def test_agent_model_in_models():
    assert "agentguard-agent" in MODELS


def test_agent_claude_haiku_in_models():
    assert "agentguard-agent-claude-haiku" in MODELS


def test_rag_claude_haiku_in_models():
    assert "agentguard-rag-claude-haiku" in MODELS


def test_agent_models_set():
    assert "agentguard-agent" in AGENT_MODELS
    assert "agentguard-agent-claude-haiku" in AGENT_MODELS


def test_agent_model_in_model_list():
    result = get_model_list()
    ids = [m["id"] for m in result["data"]]
    assert "agentguard-agent" in ids
    assert "agentguard-agent-claude-haiku" in ids
    assert "agentguard-rag-claude-haiku" in ids


def test_call_returns_tuple():
    with patch("app.agent.graph.run_agent_async", new=Mock(return_value="ignored")), \
         patch("app.api.services.agent_llm.asyncio.run", return_value="agent answer"):
        from app.api.services import agent_llm
        result, cid = agent_llm.call(
            query="hello",
            chat_id="chat-abc",
            user_id=None,
            request_id="req-001",
        )

    assert result == "agent answer"
    assert cid.startswith("chatcmpl-")


def test_call_returns_list_answer():
    raw = [{"text": "part1"}, {"text": "part2"}]
    with patch("app.agent.graph.run_agent_async", new=Mock(return_value="ignored")), \
         patch("app.api.services.agent_llm.asyncio.run", return_value=raw):
        from app.api.services import agent_llm
        result, cid = agent_llm.call(
            query="hello",
            chat_id="chat-abc",
            user_id=None,
            request_id="req-001",
        )

    assert result == "part1part2"
    assert cid.startswith("chatcmpl-")


def test_call_uses_provided_model():
    with patch("app.agent.graph.run_agent_async", new=Mock(return_value="ignored")) as mock_async, \
         patch("app.api.services.agent_llm.asyncio.run", return_value="ok") as mock_run:
        from app.api.services import agent_llm
        result, cid = agent_llm.call(
            query="hello",
            chat_id="chat-abc",
            user_id=None,
            request_id="req-001",
            model="openrouter-claude-haiku",
        )

    mock_run.assert_called_once()
    mock_async.assert_called_once_with(
        question="hello",
        model="openrouter-claude-haiku",
        checkpointer=None,
    )
    assert result == "ok"
    assert cid.startswith("chatcmpl-")


def test_call_returns_error_string_on_exception():
    with patch("app.agent.graph.run_agent_async", new=Mock(return_value="ignored")), \
         patch("app.api.services.agent_llm.asyncio.run", side_effect=RuntimeError("boom")):
        from app.api.services import agent_llm
        result, cid = agent_llm.call(
            query="hello",
            chat_id="chat-err",
            user_id=None,
            request_id="req-err",
        )

    assert "[Error:" in result
    assert cid.startswith("chatcmpl-")


@pytest.mark.asyncio
async def test_chat_service_routes_agent_model():
    from app.api.schemas import ChatRequest, Message
    from app.api.services import chat_service

    body = ChatRequest(
        model="agentguard-agent",
        messages=[Message(role="user", content="what tools do you have?")],
    )

    with patch("app.api.services.agent_llm.call", return_value=("tool answer", "chatcmpl-xyz")) as mock_call:
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
        model="openrouter-gemini-flash",
    )
    assert result == "tool answer"
    assert cid == "chatcmpl-xyz"


@pytest.mark.asyncio
async def test_chat_service_routes_agent_claude_haiku():
    from app.api.schemas import ChatRequest, Message
    from app.api.services import chat_service

    body = ChatRequest(
        model="agentguard-agent-claude-haiku",
        messages=[Message(role="user", content="list repos")],
    )

    with patch("app.api.services.agent_llm.call", return_value=("haiku answer", "chatcmpl-haiku")) as mock_call:
        result, cid = await chat_service.complete(
            body=body,
            query="list repos",
            chat_id="chat-456",
            request_id="req-haiku",
        )

    mock_call.assert_called_once_with(
        query="list repos",
        chat_id="chat-456",
        user_id=None,
        request_id="req-haiku",
        model="openrouter-claude-haiku",
    )
    assert result == "haiku answer"
    assert cid == "chatcmpl-haiku"
