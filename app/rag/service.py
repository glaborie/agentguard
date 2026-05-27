from app.rag.chain import build_rag_chain
from app.rag.chain import query as _query
from app.rag.ingest import ingest as _ingest


def ingest(chunk_size: int = 800, chunk_overlap: int = 200) -> None:
    _ingest(chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def query(question: str, model: str | None = None, callbacks: list | None = None) -> str:
    return _query(question=question, model=model, callbacks=callbacks)


def build_chain(model: str | None = None, k: int = 4):
    return build_rag_chain(model=model, k=k)
