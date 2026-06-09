"""Hybrid retriever: ensemble of vector (Qdrant) and BM25 keyword search via RRF.

The vector half is the existing ``ScoredRetriever`` (untouched, still emits the four
``retrieval.*`` OTel span attributes). The BM25 half is built once from Qdrant and
cached by ``app.rag.bm25_index``. ``EnsembleRetriever`` (langchain) applies weighted
Reciprocal Rank Fusion to merge the two rank lists; it dedupes by ``page_content`` so
a chunk that both retrievers surface contributes its RRF score from both ranks.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain.retrievers import EnsembleRetriever
from opentelemetry import trace as otel_trace
from pydantic import ConfigDict

logger = logging.getLogger(__name__)


class HybridRetriever(BaseRetriever):
    """Ensemble of vector + BM25 retrievers with RRF fusion.

    The wrapper exists for three reasons:
    1. Emits ``retrieval.mode = "hybrid"`` on the OTel span.
    2. Slices the ensemble's deduped output down to ``k`` so the downstream prompt
       receives a bounded context.
    3. Carries the ``ScoredRetriever`` so its existing OTel attribute writes (min/max/avg
       score) keep firing via the run_manager callback chain.
    """

    vector_retriever: Any
    bm25_retriever: Any
    k: int = 6
    vector_weight: float = 0.5
    bm25_weight: float = 0.5
    rrf_c: int = 60
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        ensemble = EnsembleRetriever(
            retrievers=[self.vector_retriever, self.bm25_retriever],
            weights=[self.vector_weight, self.bm25_weight],
            c=self.rrf_c,
        )
        # Child tag lets the two sub-retrievers appear as nested spans in the trace
        # (e.g. "EnsembleRetriever > retriever_1 (ScoredRetriever) > retriever_2 (BM25Retriever)").
        docs = ensemble.invoke(
            query,
            config={"callbacks": run_manager.get_child(tag="hybrid_ensemble")},
        )
        sliced = docs[: self.k]

        span = otel_trace.get_current_span()
        if span.is_recording():
            span.set_attribute("retrieval.mode", "hybrid")
            span.set_attribute("retrieval.k", self.k)
            span.set_attribute("retrieval.result_count", len(sliced))

        return sliced
