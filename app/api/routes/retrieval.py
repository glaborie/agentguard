"""Retrieval debugging API endpoint."""

from __future__ import annotations

import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class RetrievalDebugRequest(BaseModel):
    query: str
    k: int = 6
    mode: Literal["vector", "hybrid", "compare"] = "compare"


def _build_retrievers(k: int, mode: str) -> dict:
    from app.config import settings
    from app.rag.bm25_index import build_or_load
    from app.rag.chain import ScoredRetriever
    from app.rag.hybrid_retriever import HybridRetriever
    from langchain_openai import OpenAIEmbeddings
    from langchain_qdrant import QdrantVectorStore
    from qdrant_client import QdrantClient

    embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        openai_api_base=f"{settings.litellm_base_url}/v1",
        openai_api_key=settings.litellm_master_key,
    )
    client = QdrantClient(url=settings.qdrant_url)
    vector_store = QdrantVectorStore(
        client=client,
        collection_name=settings.qdrant_collection,
        embedding=embeddings,
    )
    vector_ret = ScoredRetriever(vector_store=vector_store, k=k)

    if mode == "vector":
        return {"vector": vector_ret}

    bm25 = build_or_load(client, settings.qdrant_collection)
    bm25.k = max(k, 12)
    hybrid_ret = HybridRetriever(
        vector_retriever=vector_ret,
        bm25_retriever=bm25,
        k=k,
    )

    if mode == "hybrid":
        return {"hybrid": hybrid_ret}

    return {"vector": vector_ret, "hybrid": hybrid_ret}


def _run(retriever, query: str) -> tuple[list[dict[str, Any]], float]:
    t0 = time.perf_counter()
    docs = retriever.invoke(query)
    ms = round((time.perf_counter() - t0) * 1000, 1)
    chunks = [
        {
            "rank": i + 1,
            "score": doc.metadata.get("retrieval_score"),
            "source": doc.metadata.get("source", "unknown"),
            "text": doc.page_content[:500],
        }
        for i, doc in enumerate(docs)
    ]
    return chunks, ms


@router.post("/api/retrieval/debug")
async def debug_retrieval(req: RetrievalDebugRequest) -> dict[str, Any]:
    try:
        retrievers = _build_retrievers(req.k, req.mode)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Retriever init failed: {exc}") from exc

    results: dict[str, Any] = {}
    for label, ret in retrievers.items():
        chunks, ms = _run(ret, req.query)
        results[label] = {"chunks": chunks, "ms": ms}

    if req.mode == "compare":
        v_srcs = {c["source"] for c in results["vector"]["chunks"]}
        h_srcs = {c["source"] for c in results["hybrid"]["chunks"]}
        results["diff"] = {
            "only_hybrid": sorted(h_srcs - v_srcs),
            "only_vector": sorted(v_srcs - h_srcs),
            "common": sorted(v_srcs & h_srcs),
        }

    return {"query": req.query, "k": req.k, "mode": req.mode, "results": results}
