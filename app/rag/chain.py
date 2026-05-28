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

from app.config import settings
from app.tracing import get_langfuse_client

RAG_SYSTEM_PROMPT = """\
You are a helpful sales assistant for NorthstarCRM. \
Answer questions about products, pricing, policies, and sales processes \
using ONLY the provided context. \
If the context doesn't contain enough information to answer accurately, say so honestly. \
Do not invent pricing, discounts, features, or policies not mentioned in the context. \
When you must decline a request or cannot fulfill it directly, \
always offer to connect the customer with the account executive or sales team who can help further.

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


def get_llm(
    model: str | None = None,
    temperature: float = 0.0,
    guardrails_enabled: bool = True,
) -> ChatOpenAI:
    extra_body: dict | None = {"guardrails": []} if not guardrails_enabled else None
    return ChatOpenAI(
        model=model or settings.default_model,
        base_url=f"{settings.litellm_base_url}/v1",
        api_key=settings.litellm_master_key,
        temperature=temperature,
        **({"extra_body": extra_body} if extra_body is not None else {}),
    )


def get_retriever(k: int = 6) -> ScoredRetriever:
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
    return ScoredRetriever(vector_store=vector_store, k=k)


def format_docs(docs) -> str:
    return "\n\n---\n\n".join(
        f"[Source: {doc.metadata.get('source', 'unknown')} | Score: {doc.metadata.get('retrieval_score', 'n/a')}]\n{doc.page_content}"
        for doc in docs
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
    k: int = 4,
    guardrails_enabled: bool = True,
):
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
