"""Runtime feature flags — read/write runtime_config.json at project root.

FastAPI reads/writes this file. LiteLLM container reads it via Docker volume mount.
Changes take effect immediately for guardrails (per-call reads); semantic cache
enabled/threshold/TTL also re-read per call.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FLAGS_FILE = Path(__file__).parents[2] / "runtime_config.json"

DEFAULTS: dict[str, Any] = {
    # Semantic injection second pass
    "semantic_guard_enabled": False,
    "semantic_guard_model": "openrouter-gemini-flash",
    "semantic_guard_timeout": 8.0,
    # Toxicity detection
    "toxicity_guard_enabled": False,
    "toxicity_guard_model": "openrouter-gemini-flash",
    "toxicity_guard_timeout": 8.0,
    # Semantic cache
    "semantic_cache_enabled": True,
    "semantic_cache_threshold": 0.85,
    "semantic_cache_ttl": 3600,
    # Observability
    "langfuse_tracing_enabled": True,
    "otel_enabled": True,
    # LLM defaults
    "default_model": "openrouter-gemini-flash",
    "agent_model": "openrouter-mistral",
    # Hybrid retrieval (BM25 + vector RRF)
    "hybrid_search_enabled": True,
    "hybrid_search_vector_weight": 0.5,
    "hybrid_search_bm25_weight": 0.5,
    "hybrid_search_rrf_c": 60,
}

AVAILABLE_MODELS = [
    "openrouter-gemini-flash",
    "openrouter-mistral",
]


def _load_overrides() -> dict[str, Any]:
    if _FLAGS_FILE.exists():
        try:
            return json.loads(_FLAGS_FILE.read_text())
        except Exception as e:
            logger.warning("Failed to read runtime_config.json: %s", e)
    return {}


def get_flags() -> dict[str, Any]:
    return {**DEFAULTS, **_load_overrides()}


def update_flags(updates: dict[str, Any]) -> dict[str, Any]:
    current = _load_overrides()
    for k, v in updates.items():
        if k in DEFAULTS:
            current[k] = v
    _FLAGS_FILE.write_text(json.dumps(current, indent=2))
    return get_flags()


def reset_flags() -> dict[str, Any]:
    if _FLAGS_FILE.exists():
        _FLAGS_FILE.unlink()
    return get_flags()
