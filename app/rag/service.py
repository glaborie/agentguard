from typing import Any

from langfuse import propagate_attributes

from app.rag.chain import build_rag_chain
from app.rag.chain import query as _query
from app.rag.ingest import ingest as _ingest


def ingest(
    corpus_dir: str | None = None,
    chunk_size: int = 800,
    chunk_overlap: int = 200,
) -> None:
    _ingest(corpus_dir=corpus_dir, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def query(
    question: str,
    model: str | None = None,
    callbacks: list | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> str:
    with propagate_attributes(
        trace_name="rag-query",
        session_id=session_id,
        user_id=user_id,
        tags=["rag", "cli"],
    ):
        return _query(question=question, model=model, callbacks=callbacks)


def build_chain(model: str | None = None, k: int = 4) -> Any:
    return build_rag_chain(model=model, k=k)
