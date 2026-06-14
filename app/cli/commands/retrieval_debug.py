"""CLI command: debug-retrieval — inspect retrieved chunks for a query."""

from __future__ import annotations

import json
import time
from argparse import Namespace


def register(sub) -> None:
    p = sub.add_parser(
        "debug-retrieval",
        help="Show retrieved chunks with scores for a query",
    )
    p.add_argument("question", help="Query to debug")
    p.add_argument("--k", type=int, default=6, help="Number of chunks to retrieve (default: 6)")
    p.add_argument(
        "--mode",
        choices=["vector", "hybrid", "compare"],
        default="compare",
        help="Retriever mode (default: compare)",
    )
    p.add_argument("--json", action="store_true", help="Output raw JSON instead of table")
    p.set_defaults(func=cmd_debug_retrieval)


def _build_retrievers(k: int, mode: str):
    from app.core.config import settings
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


def _run(retriever, query: str):
    t0 = time.perf_counter()
    docs = retriever.invoke(query)
    ms = round((time.perf_counter() - t0) * 1000, 1)
    chunks = [
        {
            "rank": i + 1,
            "score": doc.metadata.get("retrieval_score"),
            "source": doc.metadata.get("source", "unknown"),
            "text": doc.page_content[:300],
        }
        for i, doc in enumerate(docs)
    ]
    return chunks, ms


def _print_table(mode_label: str, chunks: list[dict], ms: float) -> None:
    print(f"\n{'─'*70}")
    print(f"  {mode_label.upper()} retrieval  ({ms} ms)")
    print(f"{'─'*70}")
    print(f"  {'#':<4} {'Score':<8} {'Source':<35} {'Preview'}")
    print(f"  {'─'*4} {'─'*8} {'─'*35} {'─'*20}")
    for c in chunks:
        score = f"{c['score']:.4f}" if c["score"] is not None else "n/a"
        src = (c["source"] or "")[-35:]
        preview = c["text"].replace("\n", " ")[:40]
        print(f"  {c['rank']:<4} {score:<8} {src:<35} {preview}")


def cmd_debug_retrieval(args: Namespace) -> None:
    print(f"\nQuery: {args.question!r}  (k={args.k}, mode={args.mode})")

    retrievers = _build_retrievers(args.k, args.mode)
    results = {}
    for label, ret in retrievers.items():
        chunks, ms = _run(ret, args.question)
        results[label] = {"chunks": chunks, "ms": ms}

    if args.json:
        print(json.dumps(results, indent=2))
        return

    for label, data in results.items():
        _print_table(label, data["chunks"], data["ms"])

    if args.mode == "compare":
        v_srcs = {c["source"] for c in results["vector"]["chunks"]}
        h_srcs = {c["source"] for c in results["hybrid"]["chunks"]}
        only_hybrid = h_srcs - v_srcs
        only_vector = v_srcs - h_srcs
        print(f"\n  Only in hybrid : {sorted(only_hybrid) or '—'}")
        print(f"  Only in vector : {sorted(only_vector) or '—'}")
