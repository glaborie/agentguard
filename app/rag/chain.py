"""RAG chain: retrieve context from Qdrant, generate answer via LiteLLM."""

from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from opentelemetry import trace as otel_trace
from pydantic import ConfigDict
from qdrant_client import QdrantClient

from app.core.config import settings
from app.core.feature_flags import get_flags
from app.core.tracing import get_langfuse_client

RAG_SYSTEM_PROMPT = """\
You are a helpful technical assistant with expertise in IBM watsonx and related products. \
Answer questions using ONLY the provided context from the watsonx documentation. \
If the context doesn't contain enough information to answer accurately, say so honestly. \
Do not invent product features, API details, or configuration options not mentioned in the context.

Context:
{context}
"""

# Langfuse Prompt Registry fallback (mustache syntax) — mirrors RAG_SYSTEM_PROMPT.
# Used when Langfuse is unreachable and as the seed value for scripts/seed_langfuse_prompt.py.
LANGFUSE_PROMPT_MESSAGES = [
    {
        "role": "system",
        "content": RAG_SYSTEM_PROMPT.replace("{context}", "{{context}}"),
    },
    {"role": "user", "content": "{{question}}"},
]


class ScoredRetriever(BaseRetriever):
    """Retriever that surfaces Qdrant similarity scores as doc metadata and OTel span attributes."""

    vector_store: Any
    k: int = 6
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        results = self.vector_store.similarity_search_with_score(query, k=self.k)

        docs: list[Document] = []
        scores: list[float] = []
        for doc, score in results:
            doc.metadata["retrieval_score"] = round(float(score), 4)
            docs.append(doc)
            scores.append(float(score))

        span = otel_trace.get_current_span()
        if span.is_recording() and scores:
            span.set_attribute("retrieval.chunk_count", len(scores))
            span.set_attribute("retrieval.min_score", round(min(scores), 4))
            span.set_attribute("retrieval.max_score", round(max(scores), 4))
            span.set_attribute("retrieval.avg_score", round(sum(scores) / len(scores), 4))

        return docs


def _current_traceparent() -> str | None:
    """Return W3C traceparent for the active span, or None."""
    from opentelemetry import trace
    from opentelemetry.propagate import inject

    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier.get("traceparent")


def get_llm(
    model: str | None = None,
    temperature: float = 0.0,
    guardrails_enabled: bool = True,
) -> ChatOpenAI:
    extra_body: dict = {}
    if not guardrails_enabled:
        extra_body["guardrails"] = []
    return ChatOpenAI(
        model=model or settings.default_model,
        base_url=f"{settings.litellm_base_url}/v1",
        api_key=settings.litellm_master_key,  # type: ignore[arg-type]
        temperature=temperature,
        extra_body=extra_body or None,
    )



def get_retriever(k: int = 6) -> BaseRetriever:
    """Build the active retriever.

    Returns a ``HybridRetriever`` (vector + BM25 via RRF) when the
    ``hybrid_search_enabled`` flag is on — the default — and falls back to the plain
    ``ScoredRetriever`` when the flag is off. ``format_docs`` and ``build_rag_chain``
    are unchanged; both retriever types emit ``Document`` objects with the same
    ``page_content`` / ``metadata`` shape.
    """
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
    vector_retriever = ScoredRetriever(vector_store=vector_store, k=k)

    flags = get_flags()
    if not flags.get("hybrid_search_enabled", True):
        return vector_retriever

    # Lazy import: only the hybrid code path pulls in rank_bm25/langchain-community BM25.
    from app.rag.bm25_index import build_or_load
    from app.rag.hybrid_retriever import HybridRetriever

    bm25_retriever = build_or_load(client, settings.qdrant_collection)
    # Cast k up so each retriever returns enough candidates for RRF to be useful;
    # the ensemble's fused list is then sliced back to ``k`` by HybridRetriever.
    bm25_retriever.k = max(k, 12)
    return HybridRetriever(
        vector_retriever=vector_retriever,
        bm25_retriever=bm25_retriever,
        k=k,
        vector_weight=float(flags.get("hybrid_search_vector_weight", 0.5)),
        bm25_weight=float(flags.get("hybrid_search_bm25_weight", 0.5)),
        rrf_c=int(flags.get("hybrid_search_rrf_c", 60)),
    )


_MIN_CHUNK_CHARS = 150


def format_docs(docs) -> str:
    useful = [d for d in docs if len(d.page_content.strip()) >= _MIN_CHUNK_CHARS]
    if not useful:
        useful = docs  # fallback: keep all if everything is short
    return "\n\n---\n\n".join(
        f"[Source: {doc.metadata.get('source', 'unknown')} | Score: {doc.metadata.get('retrieval_score', 'n/a')}]\n{doc.page_content}"
        for doc in useful
    )


def _get_prompt_template() -> ChatPromptTemplate:
    """Fetch the RAG system prompt from Langfuse Prompt Registry.

    Falls back to LANGFUSE_PROMPT_MESSAGES if Langfuse is unreachable.
    Langfuse caches the prompt for 60 s so this adds no per-request latency.
    """
    lf_prompt = get_langfuse_client().get_prompt(
        "rag-system-prompt",
        type="chat",
        fallback=LANGFUSE_PROMPT_MESSAGES,
    )
    return ChatPromptTemplate.from_messages(lf_prompt.get_langchain_prompt())


def build_rag_chain(
    model: str | None = None,
    k: int = 10,
    guardrails_enabled: bool = True,
) -> Any:
    retriever = get_retriever(k=k)
    llm = get_llm(model=model, guardrails_enabled=guardrails_enabled)
    prompt = _get_prompt_template()

    chain = (
        {
            "context": retriever | format_docs,
            "question": RunnablePassthrough(),
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    return chain


def query(question: str, model: str | None = None, callbacks: list | None = None) -> str:
    chain = build_rag_chain(model=model)
    return chain.invoke(question, config={"callbacks": callbacks or []})


def query_with_usage(
    question: str,
    model: str | None = None,
    callbacks: list | None = None,
) -> tuple[str, dict[str, int | float]]:
    """Run RAG query and return (answer, usage_dict).

    usage_dict keys: prompt_tokens, completion_tokens, total_tokens, cost_usd.
    cost_usd comes from response_metadata["usage"]["estimated_cost"] if the proxy
    returns it, otherwise 0.0.
    """
    llm = get_llm(model=model)
    retriever = get_retriever(k=4)
    prompt = _get_prompt_template()

    # Build chain without StrOutputParser to retain AIMessage with usage metadata.
    chain_raw = (
        {
            "context": retriever | format_docs,
            "question": RunnablePassthrough(),
        }
        | prompt
        | llm
    )
    ai_message = chain_raw.invoke(question, config={"callbacks": callbacks or []})

    text = ai_message.content if hasattr(ai_message, "content") else str(ai_message)

    usage: dict[str, int | float] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}
    meta = getattr(ai_message, "response_metadata", {}) or {}
    token_usage = meta.get("token_usage") or meta.get("usage") or {}
    if token_usage:
        usage["prompt_tokens"] = int(token_usage.get("prompt_tokens", 0))
        usage["completion_tokens"] = int(token_usage.get("completion_tokens", 0))
        usage["total_tokens"] = int(token_usage.get("total_tokens", 0))
        usage["cost_usd"] = float(token_usage.get("cost", 0.0) or token_usage.get("estimated_cost", 0.0))

    return text, usage
