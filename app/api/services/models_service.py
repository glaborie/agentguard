import time

MODELS: dict[str, str] = {
    "agentguard-rag": "openrouter-gemini-flash",
    "agentguard-rag-mistral": "openrouter-mistral",
    "agentguard-direct": "openrouter-gemini-flash",
    "agentguard-agent": "openrouter-gemini-flash",
}

DIRECT_MODELS: set[str] = {"agentguard-direct"}
AGENT_MODELS: set[str] = {"agentguard-agent"}

_DESCRIPTIONS: dict[str, str] = {
    "agentguard-rag": "RAG over NorthstarCRM knowledge base (Gemini Flash)",
    "agentguard-rag-mistral": "RAG over NorthstarCRM knowledge base (Mistral)",
    "agentguard-direct": "Direct LLM — no RAG context, guardrails only",
    "agentguard-agent": "ReAct agent with tools — doc search, trace listing, scoring",
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
