"""Tests for the agent graph (app.agent.graph).

Unit tests validate graph structure and routing logic without
invoking the LLM.
"""

from unittest.mock import patch, MagicMock

from app.agent.graph import _should_continue, build_agent
from app.agent.prompts import AGENT_SYSTEM_PROMPT
from app.agent.tools import ALL_TOOLS


class TestGraphStructure:
    @patch("app.agent.graph._get_llm")
    def test_graph_compiles(self, mock_llm):
        llm = MagicMock()
        llm.bind_tools.return_value = llm
        mock_llm.return_value = llm

        graph = build_agent()
        assert graph is not None

    @patch("app.agent.graph._get_llm")
    def test_graph_has_agent_node(self, mock_llm):
        llm = MagicMock()
        llm.bind_tools.return_value = llm
        mock_llm.return_value = llm

        graph = build_agent()
        node_names = list(graph.get_graph().nodes.keys())
        assert "agent" in node_names

    @patch("app.agent.graph._get_llm")
    def test_graph_has_tools_node(self, mock_llm):
        llm = MagicMock()
        llm.bind_tools.return_value = llm
        mock_llm.return_value = llm

        graph = build_agent()
        node_names = list(graph.get_graph().nodes.keys())
        assert "tools" in node_names

    @patch("app.agent.graph._get_llm")
    def test_tools_bound_to_llm(self, mock_llm):
        llm = MagicMock()
        llm.bind_tools.return_value = llm
        mock_llm.return_value = llm

        build_agent()
        llm.bind_tools.assert_called_once_with(ALL_TOOLS)

    @patch("app.agent.graph._get_llm")
    def test_model_override(self, mock_llm):
        llm = MagicMock()
        llm.bind_tools.return_value = llm
        mock_llm.return_value = llm

        build_agent(model="openrouter-mistral")
        mock_llm.assert_called_once_with("openrouter-mistral")


class TestShouldContinue:
    def test_routes_to_tools_when_tool_calls(self):
        msg = MagicMock()
        msg.tool_calls = [{"name": "search_docs", "args": {"query": "test"}}]
        state = {"messages": [msg]}
        assert _should_continue(state) == "tools"

    def test_routes_to_end_when_no_tool_calls(self):
        msg = MagicMock()
        msg.tool_calls = []
        state = {"messages": [msg]}
        assert _should_continue(state) == "__end__"

    def test_routes_to_end_when_no_tool_calls_attr(self):
        msg = MagicMock(spec=[])
        state = {"messages": [msg]}
        assert _should_continue(state) == "__end__"


class TestSystemPrompt:
    def test_mentions_search_docs(self):
        assert "search_docs" in AGENT_SYSTEM_PROMPT

    def test_mentions_list_traces(self):
        assert "list_traces" in AGENT_SYSTEM_PROMPT

    def test_mentions_get_trace_detail(self):
        assert "get_trace_detail" in AGENT_SYSTEM_PROMPT

    def test_mentions_score_response(self):
        assert "score_response" in AGENT_SYSTEM_PROMPT

    def test_mentions_get_dataset_summary(self):
        assert "get_dataset_summary" in AGENT_SYSTEM_PROMPT
