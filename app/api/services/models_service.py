import json
import logging
import time

from app.core.config import settings

logger = logging.getLogger(__name__)

_DEFAULT_MODELS: dict[str, str] = {
    "agentguard-rag": "openrouter-gemini-flash",
    "agentguard-rag-mistral": "openrouter-mistral",
    "agentguard-rag-claude-haiku": "openrouter-claude-haiku",
    "agentguard-rag-mock": "mock-llm",
    "agentguard-direct": "openrouter-gemini-flash",
    "agentguard-agent": "openrouter-gemini-flash",
    "agentguard-agent-claude-haiku": "openrouter-claude-haiku",
}

_DEFAULT_DESCRIPTIONS: dict[str, str] = {
    "agentguard-rag": "RAG over NorthstarCRM knowledge base (Gemini Flash)",
    "agentguard-rag-mock": "RAG over NorthstarCRM knowledge base (mock-llm, load testing)",
    "agentguard-rag-mistral": "RAG over NorthstarCRM knowledge base (Mistral)",
    "agentguard-rag-claude-haiku": "RAG over NorthstarCRM knowledge base (Claude Haiku)",
    "agentguard-direct": "Direct LLM — no RAG context, guardrails only",
    "agentguard-agent": "ReAct agent with tools — doc search, trace listing, scoring",
    "agentguard-agent-claude-haiku": "ReAct agent with tools + GitHub MCP (Claude Haiku)",
}


def _parse_json_mapping(raw: str, setting_name: str) -> dict[str, str] | None:
    if not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Ignoring %s: invalid JSON (%s)", setting_name, exc)
        return None

    if not isinstance(parsed, dict):
        logger.warning("Ignoring %s: expected JSON object", setting_name)
        return None

    out: dict[str, str] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not isinstance(value, str):
            logger.warning("Ignoring non-string %s entry: %r -> %r", setting_name, key, value)
            continue
        k = key.strip()
        v = value.strip()
        if not k or not v:
            continue
        out[k] = v
    return out or None


def _parse_csv_set(raw: str, fallback: set[str]) -> set[str]:
    values = {item.strip() for item in raw.split(",") if item.strip()}
    return values or set(fallback)


_models_override = _parse_json_mapping(settings.api_models_json, "API_MODELS_JSON")
MODELS: dict[str, str] = _models_override or dict(_DEFAULT_MODELS)

_descriptions_override = _parse_json_mapping(
    settings.api_model_descriptions_json,
    "API_MODEL_DESCRIPTIONS_JSON",
)
_DESCRIPTIONS: dict[str, str] = dict(_DEFAULT_DESCRIPTIONS)
if _descriptions_override:
    _DESCRIPTIONS.update(_descriptions_override)

DIRECT_MODELS: set[str] = _parse_csv_set(
    settings.api_direct_models_csv,
    {"agentguard-direct"},
)
AGENT_MODELS: set[str] = _parse_csv_set(
    settings.api_agent_models_csv,
    {"agentguard-agent", "agentguard-agent-claude-haiku"},
)


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
