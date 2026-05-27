import time

MODELS: dict[str, str] = {
    "agentguard-rag": "openrouter-gemini-flash",
    "agentguard-rag-mistral": "openrouter-mistral",
    "agentguard-direct": "openrouter-gemini-flash",
}

DIRECT_MODELS: set[str] = {"agentguard-direct"}

_DESCRIPTIONS: dict[str, str] = {
    "agentguard-rag": "RAG over Langfuse Academy docs (Gemini Flash)",
    "agentguard-rag-mistral": "RAG over Langfuse Academy docs (Mistral)",
    "agentguard-direct": "Direct LLM — no RAG context, guardrails only",
}


def get_model_list() -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "agentguard",
                "description": _DESCRIPTIONS.get(model_id, ""),
            }
            for model_id in MODELS
        ],
    }
