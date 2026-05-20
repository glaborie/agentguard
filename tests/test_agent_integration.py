"""Integration tests for the ReAct agent (requires Docker stack)."""

import pytest

from app.agent.graph import run_agent
from app.tracing import get_langfuse_handler


@pytest.mark.integration
class TestAgentEndToEnd:
    def test_agent_answers_docs_question(self):
        answer = run_agent("What is tracing in Langfuse?")
        assert isinstance(answer, str)
        assert len(answer) > 20

    def test_agent_with_model_override(self):
        answer = run_agent("What is the AI engineering loop?", model="llama3")
        assert isinstance(answer, str)
        assert len(answer) > 20

    def test_agent_with_callbacks(self):
        handler = get_langfuse_handler()
        answer = run_agent(
            "What is monitoring in Langfuse?",
            callbacks=[handler],
        )
        assert isinstance(answer, str)
        assert len(answer) > 20

    def test_agent_handles_observability_question(self):
        answer = run_agent("List my recent traces")
        assert isinstance(answer, str)

    def test_agent_handles_unknown_topic(self):
        answer = run_agent("What is the airspeed velocity of an unladen swallow?")
        assert isinstance(answer, str)
