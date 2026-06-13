"""Tests for the RAG chain (app.rag.chain).

Unit tests for format_docs and chain construction.
Integration tests for end-to-end query (requires Docker stack).
"""

from unittest.mock import MagicMock, patch, ANY

import pytest
from langchain_core.documents import Document

from app.rag.chain import RAG_SYSTEM_PROMPT, format_docs, get_llm, _get_prompt_template


class TestFormatDocs:
    def test_formats_single_doc(self):
        doc = Document(
            page_content="NorthstarCRM supports SSO on Business and Enterprise plans.",
            metadata={"source": "02_products/feature-matrix.md"},
        )
        result = format_docs([doc])
        assert "[Source: 02_products/feature-matrix.md" in result
        assert "NorthstarCRM supports SSO" in result

    def test_formats_multiple_docs_with_separator(self):
        docs = [
            Document(page_content="First chunk.", metadata={"source": "a.md"}),
            Document(page_content="Second chunk.", metadata={"source": "b.md"}),
        ]
        result = format_docs(docs)
        assert "---" in result
        assert "First chunk." in result
        assert "Second chunk." in result
        assert "[Source: a.md" in result  # generic source label still applies
        assert "[Source: b.md" in result

    def test_handles_missing_source(self):
        doc = Document(page_content="No source.", metadata={})
        result = format_docs([doc])
        assert "[Source: unknown" in result

    def test_empty_docs(self):
        assert format_docs([]) == ""


class TestRAGPrompt:
    def test_prompt_contains_context_placeholder(self):
        assert "{context}" in RAG_SYSTEM_PROMPT

    def test_prompt_instructs_context_only(self):
        assert "ONLY" in RAG_SYSTEM_PROMPT or "only" in RAG_SYSTEM_PROMPT.lower()


class TestGetLLM:
    @patch("app.rag.chain.ChatOpenAI")
    def test_creates_llm_with_defaults(self, mock_chat):
        mock_instance = MagicMock()
        mock_chat.return_value = mock_instance

        result = get_llm()

        mock_chat.assert_called_once()
        assert result == mock_instance

    @patch("app.rag.chain.ChatOpenAI")
    def test_uses_provided_model(self, mock_chat):
        mock_instance = MagicMock()
        mock_chat.return_value = mock_instance

        get_llm(model="custom-model")

        call_args = mock_chat.call_args
        assert call_args.kwargs["model"] == "custom-model"

    @patch("app.rag.chain.ChatOpenAI")
    def test_respects_temperature(self, mock_chat):
        mock_instance = MagicMock()
        mock_chat.return_value = mock_instance

        get_llm(temperature=0.7)

        call_args = mock_chat.call_args
        assert call_args.kwargs["temperature"] == 0.7

    @patch("app.rag.chain.ChatOpenAI")
    def test_guardrails_disabled_sets_extra_body(self, mock_chat):
        mock_instance = MagicMock()
        mock_chat.return_value = mock_instance

        get_llm(guardrails_enabled=False)

        call_args = mock_chat.call_args
        assert "extra_body" in call_args.kwargs
        assert call_args.kwargs["extra_body"]["guardrails"] == []


class TestGetPromptTemplate:
    @patch("app.rag.chain.get_langfuse_client")
    def test_fetches_from_langfuse(self, mock_get_client):
        mock_client = MagicMock()
        mock_prompt_obj = MagicMock()
        mock_langchain_prompt = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "{{question}}"},
        ]
        mock_prompt_obj.get_langchain_prompt.return_value = mock_langchain_prompt
        mock_client.get_prompt.return_value = mock_prompt_obj
        mock_get_client.return_value = mock_client

        with patch("app.rag.chain.ChatPromptTemplate") as mock_template_class:
            mock_template_class.from_messages.return_value = MagicMock()
            result = _get_prompt_template()

            mock_client.get_prompt.assert_called_once()
            assert result is not None


class TestBuildRAGChain:
    @patch("app.rag.chain._get_prompt_template")
    @patch("app.rag.chain.get_llm")
    @patch("app.rag.chain.get_retriever")
    def test_builds_chain_with_defaults(self, mock_get_retriever, mock_get_llm, mock_get_prompt):
        mock_retriever = MagicMock()
        mock_llm = MagicMock()
        mock_prompt = MagicMock()

        mock_get_retriever.return_value = mock_retriever
        mock_get_llm.return_value = mock_llm
        mock_get_prompt.return_value = mock_prompt

        from app.rag.chain import build_rag_chain

        result = build_rag_chain()

        mock_get_retriever.assert_called_once_with(k=4)
        mock_get_llm.assert_called_once_with(model=None, guardrails_enabled=True)
        mock_get_prompt.assert_called_once()
        assert result is not None

    @patch("app.rag.chain._get_prompt_template")
    @patch("app.rag.chain.get_llm")
    @patch("app.rag.chain.get_retriever")
    def test_builds_chain_with_custom_k(self, mock_get_retriever, mock_get_llm, mock_get_prompt):
        mock_retriever = MagicMock()
        mock_llm = MagicMock()
        mock_prompt = MagicMock()

        mock_get_retriever.return_value = mock_retriever
        mock_get_llm.return_value = mock_llm
        mock_get_prompt.return_value = mock_prompt

        from app.rag.chain import build_rag_chain

        build_rag_chain(k=10)

        mock_get_retriever.assert_called_once_with(k=10)

    @patch("app.rag.chain._get_prompt_template")
    @patch("app.rag.chain.get_llm")
    @patch("app.rag.chain.get_retriever")
    def test_respects_guardrails_disabled(self, mock_get_retriever, mock_get_llm, mock_get_prompt):
        mock_retriever = MagicMock()
        mock_llm = MagicMock()
        mock_prompt = MagicMock()

        mock_get_retriever.return_value = mock_retriever
        mock_get_llm.return_value = mock_llm
        mock_get_prompt.return_value = mock_prompt

        from app.rag.chain import build_rag_chain

        build_rag_chain(guardrails_enabled=False)

        mock_get_llm.assert_called_once_with(model=None, guardrails_enabled=False)


class TestQueryFunctions:
    @patch("app.rag.chain.build_rag_chain")
    def test_query_invokes_chain(self, mock_build):
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "This is the answer"
        mock_build.return_value = mock_chain

        from app.rag.chain import query

        result = query("What is tracing?")

        assert result == "This is the answer"
        mock_chain.invoke.assert_called_once()

    @patch("app.rag.chain.build_rag_chain")
    def test_query_passes_model(self, mock_build):
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = "Answer"
        mock_build.return_value = mock_chain

        from app.rag.chain import query

        query("Question?", model="gpt-4")

        mock_build.assert_called_once_with(model="gpt-4")


class TestChainIntegration:
    @pytest.mark.integration
    def test_query_returns_string(self):
        from app.rag.chain import query

        result = query("What plans does NorthstarCRM offer?")
        assert isinstance(result, str)
        assert len(result) > 20

    @pytest.mark.integration
    def test_query_with_model_override(self):
        from app.rag.chain import query

        result = query("What is the discount policy?", model="openrouter-gemini-flash")
        assert isinstance(result, str)
        assert len(result) > 20

    @pytest.mark.integration
    def test_get_retriever_returns_docs(self):
        from app.rag.chain import get_retriever

        retriever = get_retriever(k=2)
        docs = retriever.invoke("What integrations are supported?")
        assert len(docs) == 2
        assert all(hasattr(d, "page_content") for d in docs)
