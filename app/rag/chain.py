"""RAG chain: retrieve context from Qdrant, generate answer via LiteLLM."""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.config import settings
from app.tracing import get_langfuse_client

RAG_SYSTEM_PROMPT = """\
You are a helpful assistant that answers questions about Langfuse \
and AI engineering practices. Use ONLY the provided context to answer. \
If the context doesn't contain enough information, say so honestly.

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


def get_llm(model: str | None = None, temperature: float = 0.0) -> ChatOpenAI:
    return ChatOpenAI(
        model=model or settings.default_model,
        base_url=f"{settings.litellm_base_url}/v1",
        api_key=settings.litellm_master_key,
        temperature=temperature,
    )


def get_retriever(k: int = 6) -> QdrantVectorStore:
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
    return vector_store.as_retriever(search_kwargs={"k": k})


def format_docs(docs) -> str:
    return "\n\n---\n\n".join(
        f"[Source: {doc.metadata.get('source', 'unknown')}]\n{doc.page_content}"
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


def build_rag_chain(model: str | None = None, k: int = 4):
    retriever = get_retriever(k=k)
    llm = get_llm(model=model)
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
