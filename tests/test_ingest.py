"""Tests for the ingestion pipeline (app.rag.ingest).

Unit tests for chunking, noise removal, and document loading from local files.
Web scraping and Qdrant storage are tested as integration tests.
"""

import tempfile
from pathlib import Path

import pytest
from langchain_core.documents import Document

from app.rag.ingest import (
    NOISE_PATTERNS,
    chunk_documents,
    load_from_directory,
    scrape_page,
)


class TestChunkDocuments:
    def test_creates_chunks(self):
        doc = Document(page_content="word " * 500, metadata={"source": "test"})
        chunks = chunk_documents([doc], chunk_size=200, overlap=50)
        assert len(chunks) > 1

    def test_preserves_metadata(self):
        doc = Document(page_content="word " * 500, metadata={"source": "test.md"})
        chunks = chunk_documents([doc], chunk_size=200, overlap=50)
        for chunk in chunks:
            assert chunk.metadata["source"] == "test.md"

    def test_respects_chunk_size(self):
        doc = Document(page_content="word " * 500, metadata={"source": "test"})
        chunks = chunk_documents([doc], chunk_size=300, overlap=50)
        for chunk in chunks:
            assert len(chunk.page_content) <= 300 + 50

    def test_single_small_doc_returns_one_chunk(self):
        doc = Document(page_content="Short text.", metadata={"source": "test"})
        chunks = chunk_documents([doc], chunk_size=1000, overlap=100)
        assert len(chunks) == 1
        assert chunks[0].page_content == "Short text."

    def test_empty_doc_list(self):
        assert chunk_documents([]) == []


class TestLoadFromDirectory:
    def test_loads_markdown_files(self, tmp_path):
        (tmp_path / "doc1.md").write_text("# Title\nContent one", encoding="utf-8")
        (tmp_path / "doc2.md").write_text("# Title\nContent two", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("not a markdown file", encoding="utf-8")

        docs = load_from_directory(tmp_path)
        assert len(docs) == 2
        sources = {d.metadata["source"] for d in docs}
        assert any("doc1.md" in s for s in sources)
        assert any("doc2.md" in s for s in sources)

    def test_empty_directory(self, tmp_path):
        docs = load_from_directory(tmp_path)
        assert docs == []

    def test_reads_content(self, tmp_path):
        (tmp_path / "test.md").write_text("Hello world", encoding="utf-8")
        docs = load_from_directory(tmp_path)
        assert docs[0].page_content == "Hello world"


class TestNoisePatterns:
    def test_noise_patterns_exist(self):
        assert len(NOISE_PATTERNS) >= 5

    def test_common_noise_included(self):
        noise_text = " ".join(NOISE_PATTERNS)
        assert "Was this page helpful?" in noise_text
        assert "Previous" in noise_text


class TestScrapePage:
    @pytest.mark.integration
    def test_scrapes_real_page(self):
        doc = scrape_page("https://langfuse.com/academy/tracing")
        assert len(doc.page_content) > 100
        assert doc.metadata["source"] == "https://langfuse.com/academy/tracing"
        for noise in NOISE_PATTERNS:
            assert noise not in doc.page_content

    @pytest.mark.integration
    def test_engineering_loop_has_summary_prefix(self):
        doc = scrape_page("https://langfuse.com/academy/ai-engineering-loop")
        assert doc.page_content.startswith("The five phases of the AI Engineering Loop")
