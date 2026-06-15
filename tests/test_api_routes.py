"""Route-level tests for app.api routes.

Uses FastAPI's TestClient; skipped automatically when fastapi is not installed.
Mocks all external I/O (httpx, Langfuse client, RAG chain) so no Docker needed.
"""

import pytest

pytest.importorskip("fastapi")

from unittest.mock import MagicMock, patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.api.app import create_app  # noqa: E402


@pytest.fixture
def client():
    with patch("app.api.app.Instrumentator"):
        app = create_app()
    return TestClient(app)


# ── probe helpers used to patch _probe ───────────────────────────────────────

async def _all_ok(name, url, headers=None):
    return name, {"status": "ok"}


async def _qdrant_down(name, url, headers=None):
    if name == "qdrant":
        return name, {"status": "error", "error": "timeout"}
    return name, {"status": "ok"}


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealthRoute:
    def setup_method(self):
        import app.api.services.health_service as hs
        hs._cached_checks = None
        hs._cached_at = 0.0

    def test_all_healthy_returns_200(self, client):
        with patch("app.api.services.health_service._probe", _all_ok):
            r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_checks_all_three_services(self, client):
        with patch("app.api.services.health_service._probe", _all_ok):
            r = client.get("/health")
        assert set(r.json()["checks"]) == {"litellm", "langfuse", "qdrant"}

    def test_degraded_service_returns_503(self, client):
        with patch("app.api.services.health_service._probe", _qdrant_down):
            r = client.get("/health")
        assert r.status_code == 503
        assert r.json()["status"] == "degraded"

    def test_degraded_names_failing_service(self, client):
        with patch("app.api.services.health_service._probe", _qdrant_down):
            r = client.get("/health")
        assert r.json()["checks"]["qdrant"]["status"] == "error"


# ── /v1/models ────────────────────────────────────────────────────────────────

class TestModelsRoute:
    def test_returns_list_object(self, client):
        r = client.get("/v1/models")
        assert r.status_code == 200
        assert r.json()["object"] == "list"

    def test_returns_seven_models(self, client):
        assert len(client.get("/v1/models").json()["data"]) == 7

    def test_expected_model_ids(self, client):
        ids = {m["id"] for m in client.get("/v1/models").json()["data"]}
        assert ids == {
            "agentguard-rag",
            "agentguard-rag-mistral",
            "agentguard-rag-claude-haiku",
            "agentguard-direct",
            "agentguard-agent",
            "agentguard-agent-claude-haiku",
            "agentguard-rag-mock",
        }

    def test_required_fields_on_every_model(self, client):
        for m in client.get("/v1/models").json()["data"]:
            assert {"id", "object", "created", "owned_by"} <= m.keys()


# ── /webhook ──────────────────────────────────────────────────────────────────

class TestWebhookRoute:
    def _lf_client(self):
        return MagicMock()

    def test_thumbs_up_scores_1(self, client):
        with patch("app.api.services.feedback_service.get_langfuse_client") as m:
            m.return_value = self._lf_client()
            r = client.post("/webhook", json={"message_id": "t-1", "rating": 1})
        assert r.json() == {"ok": True, "trace_id": "t-1", "score": 1.0}

    def test_thumbs_down_scores_0(self, client):
        with patch("app.api.services.feedback_service.get_langfuse_client") as m:
            m.return_value = self._lf_client()
            r = client.post("/webhook", json={"message_id": "t-1", "rating": -1})
        assert r.json()["score"] == 0.0

    def test_missing_message_id_returns_error(self, client):
        r = client.post("/webhook", json={"rating": 1})
        assert r.json() == {"ok": False, "error": "missing message_id or rating"}

    def test_missing_rating_returns_error(self, client):
        r = client.post("/webhook", json={"message_id": "t-1"})
        assert r.json() == {"ok": False, "error": "missing message_id or rating"}

    def test_nested_data_payload_parsed(self, client):
        with patch("app.api.services.feedback_service.get_langfuse_client") as m:
            m.return_value = self._lf_client()
            r = client.post("/webhook", json={
                "type": "feedback",
                "data": {"message_id": "t-2", "rating": 1},
            })
        assert r.json()["ok"] is True
        assert r.json()["trace_id"] == "t-2"


# ── /v1/chat/completions ──────────────────────────────────────────────────────

class TestChatCompletionsRoute:
    def _mock_rag(self, answer="Test answer", trace_id=None):
        chain = MagicMock()
        chain.invoke.return_value = answer
        handler = MagicMock()
        handler.last_trace_id = trace_id
        return chain, handler

    def test_no_user_message_returns_400(self, client):
        r = client.post("/v1/chat/completions", json={
            "model": "agentguard-rag",
            "messages": [{"role": "system", "content": "be helpful"}],
        })
        assert r.status_code == 400

    def test_rag_model_returns_completion(self, client):
        chain, handler = self._mock_rag("Paris is the capital.")
        with patch("app.api.services.rag_llm.build_chain", return_value=chain), \
             patch("app.api.services.rag_llm.get_langfuse_handler", return_value=handler):
            r = client.post("/v1/chat/completions", json={
                "model": "agentguard-rag",
                "messages": [{"role": "user", "content": "What is the capital of France?"}],
            })
        assert r.status_code == 200
        body = r.json()
        assert body["object"] == "chat.completion"
        assert body["choices"][0]["message"]["content"] == "Paris is the capital."

    def test_trace_id_used_as_completion_id(self, client):
        chain, handler = self._mock_rag(trace_id="lf-trace-xyz")
        with patch("app.api.services.rag_llm.build_chain", return_value=chain), \
             patch("app.api.services.rag_llm.get_langfuse_handler", return_value=handler):
            r = client.post("/v1/chat/completions", json={
                "model": "agentguard-rag",
                "messages": [{"role": "user", "content": "question"}],
            })
        assert r.json()["id"] == "lf-trace-xyz"

    def test_streaming_returns_event_stream_content_type(self, client):
        chain, handler = self._mock_rag()
        with patch("app.api.services.rag_llm.build_chain", return_value=chain), \
             patch("app.api.services.rag_llm.get_langfuse_handler", return_value=handler):
            r = client.post("/v1/chat/completions", json={
                "model": "agentguard-rag",
                "messages": [{"role": "user", "content": "question"}],
                "stream": True,
            })
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
