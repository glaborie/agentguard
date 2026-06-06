from unittest.mock import MagicMock, patch

import pytest

from app.api.services.models_service import AGENT_MODELS, MODELS, get_model_list


def test_agent_model_in_models():
    assert "agentguard-agent" in MODELS


def test_agent_models_set():
    assert "agentguard-agent" in AGENT_MODELS


def test_agent_model_in_model_list():
    result = get_model_list()
    ids = [m["id"] for m in result["data"]]
    assert "agentguard-agent" in ids


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

    call_args = mock_graph.invoke.call_args
    config = call_args[1].get("config") or call_args[0][1]
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

    call_args = mock_graph.invoke.call_args
    config = call_args[1].get("config") or call_args[0][1]
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
    )
    assert result == "tool answer"
    assert cid == "chatcmpl-xyz"
