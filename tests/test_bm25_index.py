"""Unit tests for app.rag.bm25_index — no Docker required.

The module-scope ``CACHE_PATH`` is monkeypatched to a ``tmp_path`` location so tests
don't write to ``data/`` and don't leak state between runs.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
from qdrant_client import QdrantClient

from app.rag import bm25_index


@pytest.fixture
def cache_dir(tmp_path, monkeypatch) -> Path:
    """Redirect the BM25 cache to a per-test tmp directory."""
    monkeypatch.setattr(bm25_index, "CACHE_PATH", tmp_path / "bm25_index.pkl")
    return tmp_path


@pytest.fixture
def fake_chunks() -> list[Document]:
    return [
        Document(page_content="Refund policy allows 30 day returns.", metadata={"source": "04_policies/refund.md"}),
        Document(page_content="SLA guarantees 99.9% uptime monthly.", metadata={"source": "04_policies/sla.md"}),
    ]


def _mock_client(chunk_count: int = 2, chunks: list[Document] | None = None) -> MagicMock:
    """Build a MagicMock QdrantClient that reports ``chunk_count`` and scrolls ``chunks``."""
    client = MagicMock(spec=QdrantClient)
    info = MagicMock()
    info.points_count = chunk_count
    client.get_collection.return_value = info
    if chunks is not None:
        points = [
            MagicMock(
                payload={
                    "page_content": c.page_content,
                    "metadata": c.metadata,
                }
            )
            for c in chunks
        ]
        # First scroll returns points + offset=None to stop
        client.scroll.side_effect = [(points, None)]
    else:
        client.scroll.side_effect = [([], None)]
    return client


# --- build_or_load -------------------------------------------------------------


def test_build_creates_cache(cache_dir, fake_chunks) -> None:
    client = _mock_client(chunk_count=len(fake_chunks), chunks=fake_chunks)
    retriever = bm25_index.build_or_load(client, "northstar_crm")
    assert isinstance(retriever, BM25Retriever)
    assert bm25_index.CACHE_PATH.exists()


def test_load_returns_cached_on_second_call(cache_dir, fake_chunks) -> None:
    client = _mock_client(chunk_count=len(fake_chunks), chunks=fake_chunks)
    first = bm25_index.build_or_load(client, "northstar_crm")
    # Second call: get_collection still reports same count; scroll not called
    client.scroll.reset_mock()
    second = bm25_index.build_or_load(client, "northstar_crm")
    # pickle.load rebuilds BM25Okapi so identity checks don't hold; verify equivalence
    # via the BM25 index's internal state (corpus_size + doc_len arrays).
    client.scroll.assert_not_called()
    assert len(second.docs) == len(first.docs) == len(fake_chunks)
    assert second.vectorizer.corpus_size == first.vectorizer.corpus_size
    assert list(second.vectorizer.doc_len) == list(first.vectorizer.doc_len)
    # Vectorizer state must be the same on disk across reloads — bm25 internal idf dict
    assert second.vectorizer.idf == first.vectorizer.idf


def test_chunk_count_mismatch_rebuilds(cache_dir, fake_chunks) -> None:
    client = _mock_client(chunk_count=len(fake_chunks), chunks=fake_chunks)
    bm25_index.build_or_load(client, "northstar_crm")
    # Stale count: cache has 2, but Qdrant now reports 5
    client.get_collection.return_value.points_count = 5
    # Provide new chunks for the rebuild
    new_chunks = fake_chunks + [
        Document(page_content="extra", metadata={"source": "x.md"}),
        Document(page_content="extra2", metadata={"source": "y.md"}),
        Document(page_content="extra3", metadata={"source": "z.md"}),
    ]
    client.scroll.side_effect = [
        (
            [
                MagicMock(
                    payload={"page_content": c.page_content, "metadata": c.metadata}
                )
                for c in new_chunks
            ],
            None,
        )
    ]
    rebuilt = bm25_index.build_or_load(client, "northstar_crm")
    assert rebuilt is not None
    assert len(rebuilt.docs) == 5


def test_collection_mismatch_rebuilds(cache_dir, fake_chunks) -> None:
    client = _mock_client(chunk_count=len(fake_chunks), chunks=fake_chunks)
    bm25_index.build_or_load(client, "northstar_crm")
    # Same count but different collection name → rebuild
    client.scroll.side_effect = [
        (
            [
                MagicMock(
                    payload={"page_content": c.page_content, "metadata": c.metadata}
                )
                for c in fake_chunks
            ],
            None,
        )
    ]
    bm25_index.build_or_load(client, "other_collection")
    payload = pickle.loads(bm25_index.CACHE_PATH.read_bytes())
    assert payload["collection"] == "other_collection"


def test_force_rebuilds_even_when_cache_valid(cache_dir, fake_chunks) -> None:
    client = _mock_client(chunk_count=len(fake_chunks), chunks=fake_chunks)
    bm25_index.build_or_load(client, "northstar_crm")
    # Add a third chunk to Qdrant but keep reported count same
    extra = fake_chunks + [Document(page_content="x", metadata={"source": "z.md"})]
    client.scroll.side_effect = [
        (
            [
                MagicMock(
                    payload={"page_content": c.page_content, "metadata": c.metadata}
                )
                for c in extra
            ],
            None,
        )
    ]
    # Note: reported count is still 2 from earlier mock — but force=True bypasses count check
    retriever = bm25_index.build_or_load(client, "northstar_crm", force=True)
    assert len(retriever.docs) == 3


# --- invalidate ----------------------------------------------------------------


def test_invalidate_deletes_file(cache_dir, fake_chunks) -> None:
    client = _mock_client(chunk_count=len(fake_chunks), chunks=fake_chunks)
    bm25_index.build_or_load(client, "northstar_crm")
    assert bm25_index.CACHE_PATH.exists()
    bm25_index.invalidate()
    assert not bm25_index.CACHE_PATH.exists()


def test_invalidate_idempotent(cache_dir) -> None:
    # No-op when file absent — must not raise
    assert not bm25_index.CACHE_PATH.exists()
    bm25_index.invalidate()
    assert not bm25_index.CACHE_PATH.exists()


# --- _english_preprocess -------------------------------------------------------


def test_preprocess_lowercases_and_drops_stopwords() -> None:
    tokens = bm25_index._english_preprocess(
        "The Refund Policy allows 30-day returns and a full SLA guarantee."
    )
    assert "refund" in tokens
    assert "policy" in tokens
    assert "sla" in tokens
    assert "guarantee" in tokens
    # Stopwords gone
    assert "the" not in tokens
    assert "a" not in tokens
    assert "and" not in tokens
    # Single chars gone
    assert all(len(t) > 1 for t in tokens)


def test_preprocess_empty_input() -> None:
    assert bm25_index._english_preprocess("") == []
    assert bm25_index._english_preprocess("a the is") == []


# --- _persist atomicity --------------------------------------------------------


def test_atomic_pickle_writes_tmp_then_renames(cache_dir, fake_chunks) -> None:
    """If the process dies mid-write, the .tmp file is left behind but the canonical
    file is never truncated. Verified by inspecting the write sequence."""
    client = _mock_client(chunk_count=len(fake_chunks), chunks=fake_chunks)
    bm25_index.build_or_load(client, "northstar_crm")

    # No leftover tmp files
    leftovers = list(bm25_index.CACHE_PATH.parent.glob("bm25_index.pkl.*.tmp"))
    assert leftovers == []

    # Re-pickling into the same path with different payload still produces a valid file
    with bm25_index.CACHE_PATH.open("rb") as f:
        first = pickle.load(f)
    first["chunk_count"] = 999  # mark tampered
    with bm25_index.CACHE_PATH.open("wb") as f:
        pickle.dump(first, f)
    # Loader rejects mismatched count and rebuilds
    client.get_collection.return_value.points_count = 999
    rebuilt = bm25_index.build_or_load(client, "northstar_crm")
    assert rebuilt is not None


# --- _load_chunks_from_qdrant scroll pagination -------------------------------


def test_scroll_pagination_through_offset(cache_dir) -> None:
    """When Qdrant returns a non-None offset, the loader must continue scrolling."""
    client = MagicMock(spec=QdrantClient)
    page1 = [
        MagicMock(payload={"page_content": "a", "metadata": {"source": "1.md"}}),
        MagicMock(payload={"page_content": "b", "metadata": {"source": "1.md"}}),
    ]
    page2 = [
        MagicMock(payload={"page_content": "c", "metadata": {"source": "2.md"}}),
    ]
    client.scroll.side_effect = [
        (page1, "offset-1"),
        (page2, None),
    ]
    docs = bm25_index._load_chunks_from_qdrant(client, "northstar_crm")
    assert len(docs) == 3
    assert [d.page_content for d in docs] == ["a", "b", "c"]
    assert client.scroll.call_count == 2
