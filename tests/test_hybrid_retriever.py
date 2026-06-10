"""Unit tests for app.rag.hybrid_retriever — mocks both halves, no Docker required."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from app.rag.hybrid_retriever import HybridRetriever


def _doc(content: str, source: str = "x.md", line: int | None = None) -> Document:
    md = {"source": source}
    if line is not None:
        md["line"] = line
    return Document(page_content=content, metadata=md)


def _fake_run_manager() -> MagicMock:
    """Build a run_manager whose get_child() returns a fresh MagicMock (used as callbacks)."""
    rm = MagicMock()
    rm.get_child.return_value = MagicMock()
    return rm


# --- construction --------------------------------------------------------------


def test_is_base_retriever_subclass() -> None:
    assert issubclass(HybridRetriever, BaseRetriever)


def test_construction_with_weights_and_c() -> None:
    v = MagicMock()
    b = MagicMock()
    r = HybridRetriever(
        vector_retriever=v,
        bm25_retriever=b,
        k=8,
        vector_weight=0.7,
        bm25_weight=0.3,
        rrf_c=30,
    )
    assert r.k == 8
    assert r.vector_weight == 0.7
    assert r.bm25_weight == 0.3
    assert r.rrf_c == 30
    assert r.vector_retriever is v
    assert r.bm25_retriever is b


# --- core behavior -------------------------------------------------------------


def test_returns_top_k() -> None:
    """Ensemble returns 10 docs; HybridRetriever slices to k=4."""
    docs = [_doc(f"doc {i}", source=f"{i}.md") for i in range(10)]
    hybrid = HybridRetriever(
        vector_retriever=MagicMock(),
        bm25_retriever=MagicMock(),
        k=4,
    )
    with patch("app.rag.hybrid_retriever.EnsembleRetriever") as ensemble_cls:
        ensemble = MagicMock()
        ensemble.invoke.return_value = docs
        ensemble_cls.return_value = ensemble
        result = hybrid._get_relevant_documents("query", run_manager=_fake_run_manager())
    assert len(result) == 4
    assert result == docs[:4]


def test_dedupes_via_ensemble_page_content_key() -> None:
    """EnsembleRetriever dedupes by page_content; HybridRetriever trusts it."""
    dup1 = _doc("refund policy text", source="policies.md", line=1)
    dup2 = _doc("refund policy text", source="policies.md", line=2)  # same content
    unique = _doc("SLA text", source="sla.md")
    hybrid = HybridRetriever(
        vector_retriever=MagicMock(),
        bm25_retriever=MagicMock(),
        k=10,
    )
    with patch("app.rag.hybrid_retriever.EnsembleRetriever") as ensemble_cls:
        ensemble = MagicMock()
        ensemble.invoke.return_value = [dup1, dup2, unique]
        ensemble_cls.return_value = ensemble
        result = hybrid._get_relevant_documents("refund", run_manager=_fake_run_manager())
    # The ensemble returns its own deduped list; HybridRetriever slices it as-is.
    assert len(result) == 3
    assert result[0].page_content == "refund policy text"


def test_otel_attr_set() -> None:
    """retrieval.mode = 'hybrid' must be written to the current OTel span."""
    docs = [_doc("a"), _doc("b")]
    hybrid = HybridRetriever(
        vector_retriever=MagicMock(),
        bm25_retriever=MagicMock(),
        k=4,
    )
    fake_span = MagicMock()
    fake_span.is_recording.return_value = True
    with (
        patch("app.rag.hybrid_retriever.EnsembleRetriever") as ensemble_cls,
        patch(
            "app.rag.hybrid_retriever.otel_trace.get_current_span",
            return_value=fake_span,
        ),
    ):
        ensemble = MagicMock()
        ensemble.invoke.return_value = docs
        ensemble_cls.return_value = ensemble
        hybrid._get_relevant_documents("q", run_manager=_fake_run_manager())

    attrs = {call.args[0]: call.args[1] for call in fake_span.set_attribute.call_args_list}
    assert attrs.get("retrieval.mode") == "hybrid"
    assert attrs.get("retrieval.k") == 4
    assert attrs.get("retrieval.result_count") == 2


def test_otel_attrs_skipped_when_span_not_recording() -> None:
    docs = [_doc("a")]
    hybrid = HybridRetriever(
        vector_retriever=MagicMock(),
        bm25_retriever=MagicMock(),
        k=4,
    )
    fake_span = MagicMock()
    fake_span.is_recording.return_value = False
    with (
        patch("app.rag.hybrid_retriever.EnsembleRetriever") as ensemble_cls,
        patch(
            "app.rag.hybrid_retriever.otel_trace.get_current_span",
            return_value=fake_span,
        ),
    ):
        ensemble = MagicMock()
        ensemble.invoke.return_value = docs
        ensemble_cls.return_value = ensemble
        hybrid._get_relevant_documents("q", run_manager=_fake_run_manager())
    fake_span.set_attribute.assert_not_called()


def test_bm25_only_doc_keeps_score_marker() -> None:
    """A doc the vector retriever never surfaced carries no retrieval_score;
    format_docs prints 'n/a' for it. HybridRetriever should not invent a score."""
    bm25_doc = _doc("refund details", source="04_policies/refund.md")
    # metadata has no retrieval_score key
    assert "retrieval_score" not in bm25_doc.metadata

    hybrid = HybridRetriever(
        vector_retriever=MagicMock(),
        bm25_retriever=MagicMock(),
        k=4,
    )
    with patch("app.rag.hybrid_retriever.EnsembleRetriever") as ensemble_cls:
        ensemble = MagicMock()
        ensemble.invoke.return_value = [bm25_doc]
        ensemble_cls.return_value = ensemble
        result = hybrid._get_relevant_documents("refund", run_manager=_fake_run_manager())
    assert result[0].metadata.get("retrieval_score", "n/a") == "n/a"


def test_empty_results_returns_empty_list() -> None:
    hybrid = HybridRetriever(
        vector_retriever=MagicMock(),
        bm25_retriever=MagicMock(),
        k=4,
    )
    with patch("app.rag.hybrid_retriever.EnsembleRetriever") as ensemble_cls:
        ensemble = MagicMock()
        ensemble.invoke.return_value = []
        ensemble_cls.return_value = ensemble
        result = hybrid._get_relevant_documents("nothing", run_manager=_fake_run_manager())
    assert result == []


def test_invoke_delegates_to_ensemble() -> None:
    """The EnsembleRetriever is constructed with the two sub-retrievers and invoked."""
    v = MagicMock()
    b = MagicMock()
    hybrid = HybridRetriever(vector_retriever=v, bm25_retriever=b, k=5)
    with patch("app.rag.hybrid_retriever.EnsembleRetriever") as ensemble_cls:
        ensemble = MagicMock()
        ensemble.invoke.return_value = [_doc("a")]
        ensemble_cls.return_value = ensemble
        hybrid._get_relevant_documents("q", run_manager=_fake_run_manager())

    ensemble_cls.assert_called_once()
    call_kwargs = ensemble_cls.call_args.kwargs
    assert call_kwargs["retrievers"] == [v, b]
    assert call_kwargs["c"] == 60
    # weights default to 0.5/0.5
    assert call_kwargs["weights"] == [0.5, 0.5]
    ensemble.invoke.assert_called_once()


def test_ensemble_uses_configured_rrf_c() -> None:
    """When c=30 is configured, EnsembleRetriever gets c=30."""
    hybrid = HybridRetriever(
        vector_retriever=MagicMock(),
        bm25_retriever=MagicMock(),
        k=5,
        rrf_c=30,
    )
    with patch("app.rag.hybrid_retriever.EnsembleRetriever") as ensemble_cls:
        ensemble = MagicMock()
        ensemble.invoke.return_value = []
        ensemble_cls.return_value = ensemble
        hybrid._get_relevant_documents("q", run_manager=_fake_run_manager())
    assert ensemble_cls.call_args.kwargs["c"] == 30


def test_ensemble_uses_configured_weights() -> None:
    """Asymmetric weights flow through to the EnsembleRetriever."""
    hybrid = HybridRetriever(
        vector_retriever=MagicMock(),
        bm25_retriever=MagicMock(),
        k=5,
        vector_weight=0.7,
        bm25_weight=0.3,
    )
    with patch("app.rag.hybrid_retriever.EnsembleRetriever") as ensemble_cls:
        ensemble = MagicMock()
        ensemble.invoke.return_value = []
        ensemble_cls.return_value = ensemble
        hybrid._get_relevant_documents("q", run_manager=_fake_run_manager())
    assert ensemble_cls.call_args.kwargs["weights"] == [0.7, 0.3]


def test_format_docs_integration_unchanged() -> None:
    """format_docs (from app.rag.chain) reads retrieval_score from metadata.
    A BM25-only doc with no score must render as 'n/a' — confirm end-to-end."""
    from app.rag.chain import format_docs

    hybrid = HybridRetriever(
        vector_retriever=MagicMock(),
        bm25_retriever=MagicMock(),
        k=4,
    )
    bm25_only = _doc("Refund policy text", source="04_policies/refund.md")
    with patch("app.rag.hybrid_retriever.EnsembleRetriever") as ensemble_cls:
        ensemble = MagicMock()
        ensemble.invoke.return_value = [bm25_only]
        ensemble_cls.return_value = ensemble
        result = hybrid._get_relevant_documents("refund", run_manager=_fake_run_manager())
    rendered = format_docs(result)
    assert "Score: n/a" in rendered
    assert "04_policies/refund.md" in rendered
