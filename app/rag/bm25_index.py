"""In-memory BM25 index for hybrid retrieval.

The BM25 index is built lazily from the chunks Qdrant already holds and pickled to
``data/bm25_index.pkl``. The cache is invalidated by ``app.rag.ingest.ingest()`` whenever
the corpus is re-ingested.

Why a side index and not Qdrant sparse vectors: the POC corpus is 35 files / a few
hundred chunks — in-memory BM25 is sub-millisecond per query, the pickle is < 1 MB,
and the index survives app restarts. A future migration to Qdrant native sparse vectors
is a single swap in ``app.rag.chain.get_retriever``; the ``HybridRetriever`` contract
does not change.
"""

from __future__ import annotations

import logging
import pickle
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
from qdrant_client import QdrantClient

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Cache location. ``data/`` already exists at project root (gitignored for corpus docs).
CACHE_PATH = Path("data") / "bm25_index.pkl"
CACHE_VERSION = 1

# Small inline stopword set — keeps the index small and the matching focused on
# content-bearing tokens. NLTK or spacy would be heavier than this corpus warrants.
_STOPWORDS: frozenset[str] = frozenset(
    """
    a an the and or but if then else of in on at to for from by with as is are was were
    be been being have has had do does did this that these those it its
    i you he she we they me him her us them my your his their our
    not no so too very can will would should could may might shall
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _english_preprocess(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric, drop stopwords and short tokens."""
    tokens = _TOKEN_RE.findall(text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def _load_chunks_from_qdrant(client: QdrantClient, collection: str) -> list[Document]:
    """Scroll every point in the collection and reconstruct a Document per chunk.

    Qdrant stores chunk text under ``page_content`` (langchain-qdrant default) and the
    original ingest metadata under ``metadata``. Falls back to the full payload when the
    wrapped layout is absent.
    """
    docs: list[Document] = []
    offset: Any = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            page_content = payload.get("page_content") or payload.get("text") or ""
            metadata = dict(payload.get("metadata") or {})
            # langchain-qdrant sets both page_content and metadata on payload
            if not metadata and "source" in payload:
                metadata = {"source": payload["source"]}
                if "line" in payload:
                    metadata["line"] = payload["line"]
            if not page_content:
                # Some ingest paths put the chunk text directly on the payload root
                page_content = " ".join(
                    f"{k}: {v}" for k, v in payload.items() if k not in {"metadata"}
                )
            docs.append(Document(page_content=page_content, metadata=metadata))
        if next_offset is None:
            break
        offset = next_offset
    return docs


def _persist(
    retriever: BM25Retriever,
    chunks: list[Document],
    collection: str,
) -> None:
    """Atomic pickle write: tmp file, then rename. Crash-safe."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "collection": collection,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "vectorizer": retriever.vectorizer,
        "preprocess_func": retriever.preprocess_func,
    }
    with tempfile.NamedTemporaryFile(
        dir=CACHE_PATH.parent,
        prefix=CACHE_PATH.name + ".",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp_path = Path(tmp.name)
        pickle.dump(payload, tmp)
    tmp_path.replace(CACHE_PATH)


def _load(collection: str, chunk_count: int) -> BM25Retriever | None:
    """Load cache if it exists and matches version/collection/chunk_count. Else None."""
    if not CACHE_PATH.exists():
        return None
    try:
        with CACHE_PATH.open("rb") as f:
            payload = pickle.load(f)
    except Exception as e:
        logger.warning("BM25 cache read failed (%s) — rebuilding", e)
        return None
    if payload.get("version") != CACHE_VERSION:
        return None
    if payload.get("collection") != collection:
        return None
    if payload.get("chunk_count") != chunk_count:
        return None
    docs = payload["chunks"]
    return BM25Retriever(
        vectorizer=payload["vectorizer"],
        docs=docs,
        preprocess_func=payload["preprocess_func"],
    )


def invalidate() -> None:
    """Delete the cache file. Called by ``ingest()`` after re-populating Qdrant."""
    if CACHE_PATH.exists():
        CACHE_PATH.unlink()
        logger.info("BM25 cache invalidated: %s", CACHE_PATH)
    else:
        # Idempotent: silent no-op when file absent
        pass


def build_or_load(
    client: QdrantClient,
    collection: str,
    *,
    force: bool = False,
) -> BM25Retriever:
    """Return a BM25Retriever backed by the corpus. Caches to disk.

    ``force=True`` skips the cache and rebuilds from Qdrant (useful after schema
    changes; normal flow uses ``invalidate()`` then ``build_or_load()``).
    """
    if not force:
        # Probe Qdrant point count for the cache key. Cheap: one count call.
        info = client.get_collection(collection_name=collection)
        chunk_count = info.points_count or 0
        cached = _load(collection, chunk_count)
        if cached is not None:
            return cached

    chunks = _load_chunks_from_qdrant(client, collection)
    logger.info("Building BM25 index from %d chunks in Qdrant", len(chunks))
    retriever = BM25Retriever.from_documents(
        documents=chunks,
        preprocess_func=_english_preprocess,
    )
    _persist(retriever, chunks, collection)
    return retriever
