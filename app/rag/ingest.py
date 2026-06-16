"""Document ingestion pipeline: load → chunk → embed → store in Qdrant.

Loads markdown and JSONL files from the local corpus directory (mock_corpus/ by default).
Web scraping has been removed — the knowledge base lives entirely on disk.
"""

import json
from pathlib import Path

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.core.config import settings

# Default corpus location — relative to the project root (where `python -m app.main` is run).
DEFAULT_CORPUS_DIR = Path("mock_corpus")


def _jsonl_to_text(record: dict) -> str:
    """Render a JSONL record as human-readable text suitable for embedding."""
    lines = []
    for key, value in record.items():
        if isinstance(value, list):
            lines.append(f"{key}: {', '.join(str(v) for v in value)}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'yes' if value else 'no'}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


_EXCLUDED_DIRS = {"07_benchmark"}


def load_from_corpus(path: str | Path | None = None) -> list[Document]:
    """Recursively load all .md and .jsonl files from the corpus directory.

    Markdown files are loaded as-is.
    JSONL files are split into one Document per line, with each record
    rendered as readable key: value text.

    Directories listed in _EXCLUDED_DIRS (e.g. 07_benchmark) are skipped
    so that evaluation fixtures are never embedded into the vector store.
    """
    root = Path(path or DEFAULT_CORPUS_DIR)
    if not root.exists():
        raise FileNotFoundError(f"Corpus directory not found: {root.resolve()}")

    docs: list[Document] = []

    for filepath in sorted(root.rglob("*")):
        if not filepath.is_file():
            continue
        if any(part in _EXCLUDED_DIRS for part in filepath.relative_to(root).parts):
            continue

        rel = filepath.relative_to(root).as_posix()

        if filepath.suffix in {".md", ".txt"}:
            text = filepath.read_text(encoding="utf-8").strip()
            if text:
                docs.append(Document(page_content=text, metadata={"source": rel}))

        elif filepath.suffix == ".jsonl":
            for lineno, line in enumerate(filepath.read_text(encoding="utf-8").splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    text = _jsonl_to_text(record)
                    docs.append(
                        Document(
                            page_content=text,
                            metadata={"source": rel, "line": lineno},
                        )
                    )
                except json.JSONDecodeError:
                    continue  # skip malformed lines silently

    return docs


def load_from_directory(path: str | Path) -> list[Document]:
    """Load .md files from a single (flat) directory. Kept for backward compatibility."""
    docs = []
    for f in sorted(Path(path).glob("*.md")):
        text = f.read_text(encoding="utf-8")
        docs.append(Document(page_content=text, metadata={"source": str(f)}))
    return docs


def chunk_documents(docs: list[Document], chunk_size: int = 1200, overlap: int = 300) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_documents(docs)


def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        openai_api_base=f"{settings.litellm_base_url}/v1",
        openai_api_key=settings.litellm_master_key,
    )


def create_collection(client: QdrantClient, collection_name: str, vector_size: int = 768) -> None:
    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        print(f"  Created Qdrant collection: {collection_name}")
    else:
        print(f"  Collection already exists: {collection_name}")


def ingest(
    corpus_dir: str | Path | None = None,
    chunk_size: int = 800,
    chunk_overlap: int = 200,
) -> QdrantVectorStore:
    """Load the corpus, embed, and store in Qdrant.

    Args:
        corpus_dir: Path to the corpus directory. Defaults to mock_corpus/.
        chunk_size: Token target per chunk.
        chunk_overlap: Overlap between adjacent chunks.
    """
    print("Loading documents...")
    docs = load_from_corpus(corpus_dir)
    print(f"  Loaded {len(docs)} documents from corpus")

    print("Chunking...")
    chunks = chunk_documents(docs, chunk_size=chunk_size, overlap=chunk_overlap)
    print(f"  Created {len(chunks)} chunks")

    embeddings = get_embeddings()

    # Detect embedding dimension by embedding a test string
    test_vector = embeddings.embed_query("test")
    vector_size = len(test_vector)

    client = QdrantClient(url=settings.qdrant_url, timeout=120)
    create_collection(client, settings.rag_collection, vector_size=vector_size)

    print("Embedding and storing in Qdrant...")
    vector_store = QdrantVectorStore.from_documents(
        documents=chunks,
        embedding=embeddings,
        url=settings.qdrant_url,
        collection_name=settings.rag_collection,
        force_recreate=True,
        timeout=120,
    )
    print(f"  Stored {len(chunks)} chunks in Qdrant")

    # BM25 index mirrors the Qdrant contents; a recreate invalidates the cache so the
    # next get_retriever() rebuilds from the new chunks. Imported lazily so unit tests
    # of chunking/loading don't need rank_bm25 installed.
    from app.rag.bm25_index import invalidate
    invalidate()

    return vector_store
