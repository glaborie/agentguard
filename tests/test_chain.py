"""Tests for the RAG chain (app.rag.chain).

Unit tests for format_docs and chain construction.
Integration tests for end-to-end query (requires Docker stack).
"""

import pytest
from langchain_core.documents import Document

from app.rag.chain import RAG_SYSTEM_PROMPT, format_docs


class TestFormatDocs:
    def test_formats_single_doc(self):
        doc = Document(
            page_content="Tracing captures execution paths.",
            metadata={"source": "https://langfuse.com/academy/tracing"},
        )
        result = format_docs([doc])
        assert "[Source: https://langfuse.com/academy/tracing]" in result
        assert "Tracing captures execution paths." in result

    def test_formats_multiple_docs_with_separator(self):
        docs = [
            Document(page_content="First chunk.", metadata={"source": "a.md"}),
            Document(page_content="Second chunk.", metadata={"source": "b.md"}),
        ]
        result = format_docs(docs)
        assert "---" in result
        assert "First chunk." in result
        assert "Second chunk." in result
        assert "[Source: a.md]" in result
        assert "[Source: b.md]" in result

    def test_handles_missing_source(self):
        doc = Document(page_content="No source.", metadata={})
        result = format_docs([doc])
        assert "[Source: unknown]" in result

    def test_empty_docs(self):
        assert format_docs([]) == ""


class TestRAGPrompt:
    def test_prompt_contains_context_placeholder(self):
        assert "{context}" in RAG_SYSTEM_PROMPT

    def test_prompt_instructs_context_only(self):
        assert "ONLY" in RAG_SYSTEM_PROMPT or "only" in RAG_SYSTEM_PROMPT.lower()


class TestChainIntegration:
    @pytest.mark.integration
    def test_query_returns_string(self):
        from app.rag.chain import query

        result = query("What is tracing in Langfuse?")
        assert isinstance(result, str)
        assert len(result) > 20

    @pytest.mark.integration
    def test_query_with_model_override(self):
        from app.rag.chain import query

        result = query("What is the AI engineering loop?", model="llama3")
        assert isinstance(result, str)
        assert len(result) > 20

    @pytest.mark.integration
    def test_get_retriever_returns_docs(self):
        from app.rag.chain import get_retriever

        retriever = get_retriever(k=2)
        docs = retriever.invoke("What is tracing?")
        assert len(docs) == 2
        assert all(hasattr(d, "page_content") for d in docs)
