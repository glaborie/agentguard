"""Compare vector vs hybrid retrieval hit-rate on the gold retrieval labels.

No LLM calls — this only exercises the retriever. Useful for proving the BM25
addition helps (or at minimum doesn't regress) before promoting the hybrid default
or before pushing the flag to its rollout state.

Usage:
    python -m scripts.compare_retrieval                 # full benchmark set
    python -m scripts.compare_retrieval --limit 20      # first 20 items
    python -m scripts.compare_retrieval --k 4           # hit@4
    python -m scripts.compare_retrieval --vector-only   # skip hybrid run
    python -m scripts.compare_retrieval --hybrid-only   # skip vector run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Allow running as a script from the project root
sys.path.insert(0, str(Path(__file__).parents[1].resolve()))

from app.core.feature_flags import get_flags, update_flags
from app.eval.benchmark import (
    eval_retrieval_hit,
    load_benchmark_items,
    load_retrieval_labels,
)
from app.rag.chain import ScoredRetriever, get_retriever
from app.rag.hybrid_retriever import HybridRetriever
from app.rag.bm25_index import build_or_load
from app.core.config import settings
from qdrant_client import QdrantClient
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("compare_retrieval")


def _build_vector_retriever(k: int) -> ScoredRetriever:
    embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        openai_api_base=f"{settings.litellm_base_url}/v1",
        openai_api_key=settings.litellm_master_key,
    )
    client = QdrantClient(url=settings.qdrant_url)
    vector_store = QdrantVectorStore(
        client=client,
        collection_name=settings.rag_collection,
        embedding=embeddings,
    )
    return ScoredRetriever(vector_store=vector_store, k=k)


def _build_hybrid_retriever(k: int) -> HybridRetriever:
    client = QdrantClient(url=settings.qdrant_url)
    vector_retriever = _build_vector_retriever(k)
    bm25 = build_or_load(client, settings.rag_collection)
    bm25.k = max(k, 12)  # cast a wider net for RRF
    return HybridRetriever(
        vector_retriever=vector_retriever,
        bm25_retriever=bm25,
        k=k,
    )


def _sources(docs) -> list[str]:
    return [d.metadata.get("source", "unknown") for d in docs]


def _run(retriever, query: str) -> tuple[list[str], float]:
    start = time.perf_counter()
    docs = retriever.invoke(query)
    elapsed = time.perf_counter() - start
    return _sources(docs), elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Cap number of items (0 = all)")
    parser.add_argument("--k", type=int, default=6, help="Top-K for both retrievers")
    parser.add_argument("--vector-only", action="store_true", help="Skip the hybrid run")
    parser.add_argument("--hybrid-only", action="store_true", help="Skip the vector run")
    parser.add_argument("--json", type=str, default=None, help="Write raw results to this JSON file")
    args = parser.parse_args()

    labels = load_retrieval_labels()
    questions = load_benchmark_items()

    # Join: an item is evaluable iff it has a non-empty question AND a non-empty label list.
    items: list[tuple[str, str, list[str]]] = []
    for qid, item in questions.items():
        gold = labels.get(qid) or item.gold_docs
        if not item.question or not gold:
            continue
        items.append((qid, item.question, gold))
    if args.limit:
        items = items[: args.limit]
    if not items:
        print("No evaluable items found (need both question and gold docs).")
        return 1

    print(f"Evaluating {len(items)} items at k={args.k}")
    print(f"  vector_only={args.vector_only}  hybrid_only={args.hybrid_only}")
    print()

    # Save and override the flag so get_retriever() returns vector-only when needed.
    # (We build both retrievers directly anyway, but this keeps the rest of the app
    # consistent during the run.)
    original_flags = get_flags()
    if args.hybrid_only:
        update_flags({"hybrid_search_enabled": False})

    try:
        vector_ret = None
        if not args.hybrid_only:
            print("Building vector retriever...")
            vector_ret = _build_vector_retriever(args.k)

        hybrid_ret = None
        if not args.vector_only:
            print("Building hybrid retriever (this builds the BM25 index on first run)...")
            hybrid_ret = _build_hybrid_retriever(args.k)
    finally:
        # restore flag state
        for k, v in original_flags.items():
            update_flags({k: v})

    rows: list[dict[str, Any]] = []
    vec_hits = 0
    hyb_hits = 0
    vec_time = 0.0
    hyb_time = 0.0

    header = f"{'id':<12} {'vec':<5} {'hyb':<5} {'d':<3} {'question':<50}"
    if not args.hybrid_only:
        header = f"{'id':<12} {'vec':<5} {'hyb':<5} {'d':<3} {'q_ms':<6} {'h_ms':<6} {'question':<40}"
    print(header)
    print("-" * len(header))

    for qid, query, gold in items:
        row: dict[str, Any] = {"id": qid, "question": query, "gold": gold}

        v_hit = None
        v_ms = None
        if vector_ret is not None:
            sources, elapsed = _run(vector_ret, query)
            v_hit = eval_retrieval_hit(sources, gold)
            v_ms = round(elapsed * 1000, 1)
            vec_hits += int(v_hit)
            vec_time += elapsed
            row["vector_hit"] = v_hit
            row["vector_sources"] = sources
            row["vector_ms"] = v_ms

        h_hit = None
        h_ms = None
        if hybrid_ret is not None:
            sources, elapsed = _run(hybrid_ret, query)
            h_hit = eval_retrieval_hit(sources, gold)
            h_ms = round(elapsed * 1000, 1)
            hyb_hits += int(h_hit)
            hyb_time += elapsed
            row["hybrid_hit"] = h_hit
            row["hybrid_sources"] = sources
            row["hybrid_ms"] = h_ms

        rows.append(row)
        delta = (h_hit or 0) - (v_hit or 0)
        if args.hybrid_only:
            print(f"{qid:<12} {'-':<5} {('Y' if h_hit else 'n'):<5} {'-':<3} {query[:48]:<50}")
        elif args.vector_only:
            print(f"{qid:<12} {('Y' if v_hit else 'n'):<5} {'-':<5} {'-':<3} {query[:48]:<50}")
        else:
            print(
                f"{qid:<12} {('Y' if v_hit else 'n'):<5} {('Y' if h_hit else 'n'):<5} "
                f"{('+' if delta > 0 else (delta < 0 and '-' or '=')):<3} "
                f"{v_ms:<6} {h_ms:<6} {query[:40]:<40}"
            )

    n = len(items)
    print()
    print("=" * 60)
    print(f"Total items:        {n}")
    if vector_ret is not None:
        print(f"Vector hit@{args.k}:     {vec_hits}/{n} = {100*vec_hits/n:.1f}%   (avg {1000*vec_time/n:.1f} ms/query)")
    if hybrid_ret is not None:
        print(f"Hybrid hit@{args.k}:     {hyb_hits}/{n} = {100*hyb_hits/n:.1f}%   (avg {1000*hyb_time/n:.1f} ms/query)")
    if vector_ret is not None and hybrid_ret is not None:
        print(f"Delta:              {hyb_hits - vec_hits:+d} hits")
    print("=" * 60)

    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2))
        print(f"Wrote {len(rows)} rows to {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
