"""Tests for the ingestion pipeline (app.rag.ingest).

Unit tests for chunking, corpus loading (markdown + JSONL), and document structure.
Qdrant storage is tested as an integration test.
"""

import json
from pathlib import Path

import pytest
from langchain_core.documents import Document

from app.rag.ingest import (
    _jsonl_to_text,
    chunk_documents,
    load_from_corpus,
    load_from_directory,
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


class TestJsonlToText:
    def test_scalar_fields(self):
        result = _jsonl_to_text({"id": "q1", "question": "What is the price?"})
        assert "id: q1" in result
        assert "question: What is the price?" in result

    def test_list_fields_joined(self):
        result = _jsonl_to_text({"docs": ["a.md", "b.md"]})
        assert "docs: a.md, b.md" in result

    def test_bool_rendered_as_yes_no(self):
        result = _jsonl_to_text({"should_escalate": True})
        assert "should_escalate: yes" in result
        result2 = _jsonl_to_text({"should_escalate": False})
        assert "should_escalate: no" in result2

    def test_empty_record(self):
        assert _jsonl_to_text({}) == ""


class TestLoadFromCorpus:
    def test_loads_markdown_files(self, tmp_path):
        sub = tmp_path / "01_section"
        sub.mkdir()
        (sub / "about.md").write_text("# About\nContent here", encoding="utf-8")
        (sub / "glossary.md").write_text("# Glossary\nTerms here", encoding="utf-8")

        docs = load_from_corpus(tmp_path)
        assert len(docs) == 2

    def test_loads_jsonl_lines_as_separate_docs(self, tmp_path):
        sub = tmp_path / "06_conversations"
        sub.mkdir()
        lines = [
            json.dumps({"id": "c1", "user_message": "Can I get a discount?"}),
            json.dumps({"id": "c2", "user_message": "What is your SLA?"}),
        ]
        (sub / "examples.jsonl").write_text("\n".join(lines), encoding="utf-8")

        docs = load_from_corpus(tmp_path)
        assert len(docs) == 2
        assert all(d.metadata["source"].endswith("examples.jsonl") for d in docs)
        assert docs[0].metadata["line"] == 1
        assert docs[1].metadata["line"] == 2

    def test_jsonl_content_is_readable_text(self, tmp_path):
        (tmp_path / "q.jsonl").write_text(
            json.dumps({"question": "Do you support SSO?", "should_escalate": False}),
            encoding="utf-8",
        )
        docs = load_from_corpus(tmp_path)
        assert "question: Do you support SSO?" in docs[0].page_content
        assert "should_escalate: no" in docs[0].page_content

    def test_skips_empty_markdown(self, tmp_path):
        (tmp_path / "empty.md").write_text("   \n  ", encoding="utf-8")
        (tmp_path / "real.md").write_text("# Real content", encoding="utf-8")
        docs = load_from_corpus(tmp_path)
        assert len(docs) == 1

    def test_skips_malformed_jsonl_lines(self, tmp_path):
        (tmp_path / "data.jsonl").write_text(
            '{"id": "ok"}\nnot-json\n{"id": "also-ok"}\n', encoding="utf-8"
        )
        docs = load_from_corpus(tmp_path)
        assert len(docs) == 2

    def test_walks_subdirectories_recursively(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "b").mkdir()
        (tmp_path / "a" / "doc.md").write_text("level 1", encoding="utf-8")
        (tmp_path / "a" / "b" / "deep.md").write_text("level 2", encoding="utf-8")
        docs = load_from_corpus(tmp_path)
        assert len(docs) == 2

    def test_source_metadata_is_relative_path(self, tmp_path):
        sub = tmp_path / "01_company"
        sub.mkdir()
        (sub / "about.md").write_text("About us", encoding="utf-8")
        docs = load_from_corpus(tmp_path)
        # Normalise OS-specific separators before comparing
        source = docs[0].metadata["source"].replace("\\", "/")
        assert source == "01_company/about.md"

    def test_raises_if_corpus_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_from_corpus(tmp_path / "nonexistent")

    def test_ignores_non_md_non_jsonl_files(self, tmp_path):
        (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")
        (tmp_path / "data.csv").write_text("a,b", encoding="utf-8")
        (tmp_path / "real.md").write_text("keep me", encoding="utf-8")
        docs = load_from_corpus(tmp_path)
        assert len(docs) == 1


class TestLoadFromDirectory:
    def test_loads_markdown_files(self, tmp_path):
        (tmp_path / "doc1.md").write_text("# Title\nContent one", encoding="utf-8")
        (tmp_path / "doc2.md").write_text("# Title\nContent two", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("not a markdown file", encoding="utf-8")

        docs = load_from_directory(tmp_path)
        assert len(docs) == 2

    def test_empty_directory(self, tmp_path):
        docs = load_from_directory(tmp_path)
        assert docs == []

    def test_reads_content(self, tmp_path):
        (tmp_path / "test.md").write_text("Hello world", encoding="utf-8")
        docs = load_from_directory(tmp_path)
        assert docs[0].page_content == "Hello world"
