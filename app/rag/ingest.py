"""Document ingestion pipeline: load → chunk → embed → store in Qdrant."""

from pathlib import Path

import requests
from bs4 import BeautifulSoup
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.config import settings

LANGFUSE_ACADEMY_URLS = [
    "https://langfuse.com/academy/ai-engineering-loop",
    "https://langfuse.com/academy/tracing",
    "https://langfuse.com/academy/monitoring",
    "https://langfuse.com/academy/datasets",
    "https://langfuse.com/academy/experiments",
    "https://langfuse.com/academy/evaluate",
]


NOISE_PATTERNS = [
    "Was this page helpful?",
    "Good\nBad",
    "Support\nLast edited",
    "→ Read more",
    "→ Start with",
    "Previous\nLangfuse Academy",
]


def scrape_page(url: str) -> Document:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.body
    text = main.get_text(separator="\n", strip=True) if main else ""

    for noise in NOISE_PATTERNS:
        text = text.replace(noise, "")

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    text = "\n".join(lines)

    if "ai-engineering-loop" in url:
        summary = (
            "The five phases of the AI Engineering Loop are: "
            "1) Trace - capture the full path of requests, "
            "2) Monitor - track system behavior over time, "
            "3) Build Datasets - curate examples from production traces, "
            "4) Experiment - test prompt/model/code variants against datasets, "
            "5) Evaluate - judge results using manual review, code checks, or LLM-as-judge.\n\n"
        )
        text = summary + text

    return Document(page_content=text, metadata={"source": url})


def load_from_urls(urls: list[str] | None = None) -> list[Document]:
    urls = urls or LANGFUSE_ACADEMY_URLS
    docs = []
    for url in urls:
        print(f"  Scraping {url}")
        docs.append(scrape_page(url))
    return docs


def load_from_directory(path: str | Path) -> list[Document]:
    docs = []
    for f in Path(path).glob("*.md"):
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


def create_collection(client: QdrantClient, collection_name: str, vector_size: int = 768):
    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        print(f"  Created Qdrant collection: {collection_name}")
    else:
        print(f"  Collection already exists: {collection_name}")


def ingest(
    urls: list[str] | None = None,
    local_dir: str | Path | None = None,
    chunk_size: int = 800,
    chunk_overlap: int = 200,
) -> QdrantVectorStore:
    print("Loading documents...")
    if local_dir:
        docs = load_from_directory(local_dir)
    else:
        docs = load_from_urls(urls)
    print(f"  Loaded {len(docs)} documents")

    print("Chunking...")
    chunks = chunk_documents(docs, chunk_size=chunk_size, overlap=chunk_overlap)
    print(f"  Created {len(chunks)} chunks")

    embeddings = get_embeddings()

    # Detect embedding dimension by embedding a test string
    test_vector = embeddings.embed_query("test")
    vector_size = len(test_vector)

    client = QdrantClient(url=settings.qdrant_url)
    create_collection(client, settings.qdrant_collection, vector_size=vector_size)

    print("Embedding and storing in Qdrant...")
    vector_store = QdrantVectorStore.from_documents(
        documents=chunks,
        embedding=embeddings,
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection,
        force_recreate=True,
    )
    print(f"  Stored {len(chunks)} chunks in Qdrant")

    return vector_store
