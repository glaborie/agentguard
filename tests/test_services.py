"""Service-level unit tests.

Covers: direct_llm error mapping, rag_llm flow, health aggregation,
        webhook payload normalisation, and ID generation helpers.
No Docker required — all external I/O is mocked.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.api.services import direct_llm, feedback_service, health_service, rag_llm
from app.core import ids


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_http_client(response=None, side_effect=None):
    """Build a mock httpx.AsyncClient class whose context manager yields a
    client whose get/post returns *response* or raises *side_effect*."""
    inner = AsyncMock()
    if side_effect is not None:
        inner.get = AsyncMock(side_effect=side_effect)
        inner.post = AsyncMock(side_effect=side_effect)
    else:
        inner.get = AsyncMock(return_value=response)
        inner.post = AsyncMock(return_value=response)

    cm = AsyncMock()
    cm.__aenter__.return_value = inner
    cm.__aexit__.return_value = None

    return MagicMock(return_value=cm), inner


def _litellm_response(content="The answer"):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


# ── app.core.ids ──────────────────────────────────────────────────────────────

class TestIds:
    def test_request_id_is_12_hex_chars(self):
        rid = ids.request_id()
        assert len(rid) == 12
        assert all(c in "0123456789abcdef" for c in rid)

    def test_request_ids_are_unique(self):
        assert ids.request_id() != ids.request_id()

    def test_completion_id_has_prefix(self):
        assert ids.completion_id().startswith("chatcmpl-")

    def test_completion_id_suffix_is_8_hex_chars(self):
        suffix = ids.completion_id().removeprefix("chatcmpl-")
        assert len(suffix) == 8
        assert all(c in "0123456789abcdef" for c in suffix)

    def test_completion_ids_are_unique(self):
        assert ids.completion_id() != ids.completion_id()


# ── feedback_service: parse_feedback ─────────────────────────────────────────

class TestParseFeedback:
    def test_flat_thumbs_up(self):
        mid, score, comment = feedback_service.parse_feedback(
            {"message_id": "t-1", "rating": 1}
        )
        assert mid == "t-1"
        assert score == 1.0
        assert comment == ""

    def test_flat_thumbs_down(self):
        _, score, _ = feedback_service.parse_feedback({"message_id": "t-1", "rating": -1})
        assert score == 0.0

    def test_nested_data_payload(self):
        payload = {"type": "feedback", "data": {"message_id": "t-2", "rating": 1}}
        mid, score, _ = feedback_service.parse_feedback(payload)
        assert mid == "t-2"
        assert score == 1.0

    def test_missing_message_id_returns_none(self):
        mid, score, _ = feedback_service.parse_feedback({"rating": 1})
        assert mid is None
        assert score is None

    def test_missing_rating_returns_none(self):
        mid, _, _ = feedback_service.parse_feedback({"message_id": "t-1"})
        assert mid is None

    def test_flat_comment_extracted(self):
        _, _, comment = feedback_service.parse_feedback(
            {"message_id": "t-1", "rating": 1, "comment": "Great!"}
        )
        assert comment == "Great!"

    def test_nested_comment_extracted(self):
        payload = {
            "type": "feedback",
            "data": {"message_id": "t-1", "rating": 1, "feedback": {"comment": "Nice"}},
        }
        _, _, comment = feedback_service.parse_feedback(payload)
        assert comment == "Nice"


# ── feedback_service: handle_webhook ─────────────────────────────────────────

class TestHandleWebhook:
    def _lf(self):
        return MagicMock()

    def test_returns_ok_on_valid_payload(self):
        with patch("app.api.services.feedback_service.get_langfuse_client") as m:
            m.return_value = self._lf()
            result = feedback_service.handle_webhook({"message_id": "t-1", "rating": 1})
        assert result == {"ok": True, "trace_id": "t-1", "score": 1.0}

    def test_score_zero_for_thumbs_down(self):
        with patch("app.api.services.feedback_service.get_langfuse_client") as m:
            m.return_value = self._lf()
            result = feedback_service.handle_webhook({"message_id": "t-1", "rating": -1})
        assert result["score"] == 0.0

    def test_missing_fields_returns_error(self):
        result = feedback_service.handle_webhook({"rating": 1})
        assert result == {"ok": False, "error": "missing message_id or rating"}

    def test_push_failure_returns_error(self):
        with patch("app.api.services.feedback_service.get_langfuse_client") as m:
            m.return_value.create_score.side_effect = RuntimeError("Langfuse down")
            result = feedback_service.handle_webhook({"message_id": "t-1", "rating": 1})
        assert result["ok"] is False
        assert "Langfuse down" in result["error"]


# ── health_service: _probe ────────────────────────────────────────────────────

class TestProbe:
    def test_success_returns_ok(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        mock_class, _ = _make_http_client(response=resp)
        with patch("app.api.services.health_service.httpx.AsyncClient", mock_class):
            name, info = asyncio.run(health_service._probe("qdrant", "http://qdrant/healthz"))
        assert name == "qdrant"
        assert info == {"status": "ok"}

    def test_timeout_returns_error(self):
        mock_class, _ = _make_http_client(side_effect=httpx.TimeoutException("t/o"))
        with patch("app.api.services.health_service.httpx.AsyncClient", mock_class):
            name, info = asyncio.run(health_service._probe("langfuse", "http://lf/health"))
        assert name == "langfuse"
        assert info == {"status": "error", "error": "timeout"}

    def test_http_error_includes_status_code(self):
        err_resp = MagicMock()
        err_resp.status_code = 503
        ok_resp = MagicMock()
        ok_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "bad", request=MagicMock(), response=err_resp
        )
        mock_class, _ = _make_http_client(response=ok_resp)
        with patch("app.api.services.health_service.httpx.AsyncClient", mock_class):
            _, info = asyncio.run(health_service._probe("litellm", "http://litellm/health"))
        assert info["status"] == "error"
        assert "503" in info["error"]

    def test_generic_error_returns_error(self):
        mock_class, _ = _make_http_client(side_effect=OSError("connection refused"))
        with patch("app.api.services.health_service.httpx.AsyncClient", mock_class):
            _, info = asyncio.run(health_service._probe("qdrant", "http://qdrant/healthz"))
        assert info["status"] == "error"
        assert "connection refused" in info["error"]


# ── health_service: check_all ─────────────────────────────────────────────────

async def _probe_all_ok(name, url, headers=None):
    return name, {"status": "ok"}


async def _probe_qdrant_down(name, url, headers=None):
    if name == "qdrant":
        return name, {"status": "error", "error": "timeout"}
    return name, {"status": "ok"}


class TestCheckAll:
    def test_all_ok(self):
        with patch("app.api.services.health_service._probe", _probe_all_ok):
            checks, all_ok = asyncio.run(health_service.check_all())
        assert all_ok is True
        assert set(checks) == {"litellm", "langfuse", "qdrant"}

    def test_one_service_down_all_ok_is_false(self):
        with patch("app.api.services.health_service._probe", _probe_qdrant_down):
            checks, all_ok = asyncio.run(health_service.check_all())
        assert all_ok is False
        assert checks["qdrant"]["status"] == "error"
        assert checks["litellm"]["status"] == "ok"

    def test_checks_dict_has_three_entries(self):
        with patch("app.api.services.health_service._probe", _probe_all_ok):
            checks, _ = asyncio.run(health_service.check_all())
        assert len(checks) == 3


# ── direct_llm: call ─────────────────────────────────────────────────────────

class TestDirectLlmCall:
    def _call(self, mock_class):
        with patch("app.api.services.direct_llm.httpx.AsyncClient", mock_class):
            return asyncio.run(
                direct_llm.call(
                    [{"role": "user", "content": "Hi"}], "gpt-4o", "req-test"
                )
            )

    def test_success_returns_content_and_completion_id(self):
        mock_class, _ = _make_http_client(response=_litellm_response("Hello"))
        result, cid = self._call(mock_class)
        assert result == "Hello"
        assert cid.startswith("chatcmpl-")

    def test_timeout_returns_inline_error(self):
        mock_class, _ = _make_http_client(side_effect=httpx.TimeoutException("t/o"))
        result, _ = self._call(mock_class)
        assert result.startswith("[Error: upstream timeout]")
        assert "req-test" in result

    def test_request_error_returns_inline_error(self):
        mock_class, _ = _make_http_client(side_effect=httpx.ConnectError("refused"))
        result, _ = self._call(mock_class)
        assert result.startswith("[Error: upstream unavailable]")
        assert "req-test" in result

    def test_http_error_with_json_body(self):
        err_resp = MagicMock()
        err_resp.json.return_value = {"error": "blocked by guardrail"}
        ok_resp = MagicMock()
        ok_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "bad", request=MagicMock(), response=err_resp
        )
        mock_class, _ = _make_http_client(response=ok_resp)
        result, _ = self._call(mock_class)
        assert "blocked by guardrail" in result
        assert "req-test" in result

    def test_http_error_with_text_body(self):
        err_resp = MagicMock()
        err_resp.json.side_effect = ValueError("not json")
        err_resp.text = "Internal Server Error"
        ok_resp = MagicMock()
        ok_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "bad", request=MagicMock(), response=err_resp
        )
        mock_class, _ = _make_http_client(response=ok_resp)
        result, _ = self._call(mock_class)
        assert "Internal Server Error" in result

    def test_generic_exception_returns_inline_error(self):
        mock_class, _ = _make_http_client(side_effect=ValueError("unexpected"))
        result, _ = self._call(mock_class)
        assert "[Error:" in result
        assert "req-test" in result

    def test_always_returns_a_completion_id(self):
        mock_class, _ = _make_http_client(side_effect=httpx.TimeoutException("t/o"))
        _, cid = self._call(mock_class)
        assert cid.startswith("chatcmpl-")


# ── rag_llm: call ─────────────────────────────────────────────────────────────

class TestRagLlmCall:
    def _call(self, chain, handler):
        with patch("app.api.services.rag_llm.build_chain", return_value=chain), \
             patch("app.api.services.rag_llm.get_langfuse_handler", return_value=handler), \
             patch("app.api.services.rag_llm.propagate_attributes"):
            return asyncio.run(
                rag_llm.call(
                    "what is langfuse?", "gemini-flash", None, None, {}, "req-test"
                )
            )

    def _chain(self, text=None, exc=None):
        c = MagicMock()
        if exc is not None:
            c.invoke.side_effect = exc
        else:
            c.invoke.return_value = text
        return c

    def _handler(self, trace_id):
        h = MagicMock()
        h.last_trace_id = trace_id
        return h

    def test_success_uses_trace_id_as_completion_id(self):
        result, cid = self._call(self._chain("Paris"), self._handler("lf-abc123"))
        assert result == "Paris"
        assert cid == "lf-abc123"

    def test_no_trace_id_falls_back_to_completion_id(self):
        _, cid = self._call(self._chain("Paris"), self._handler(None))
        assert cid.startswith("chatcmpl-")

    def test_timeout_returns_inline_error(self):
        result, _ = self._call(
            self._chain(exc=httpx.TimeoutException("t/o")), self._handler(None)
        )
        assert result.startswith("[Error: upstream timeout]")
        assert "req-test" in result

    def test_request_error_returns_inline_error(self):
        result, _ = self._call(
            self._chain(exc=httpx.ConnectError("refused")), self._handler(None)
        )
        assert result.startswith("[Error: upstream unavailable]")

    def test_generic_exception_returns_inline_error(self):
        result, _ = self._call(
            self._chain(exc=RuntimeError("model crashed")), self._handler(None)
        )
        assert "[Error:" in result
        assert "req-test" in result
