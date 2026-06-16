from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "settings"]

_URL_SCHEMES = ("http://", "https://")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        validate_default=True,
    )

    # Langfuse
    langfuse_public_key: str = "pk-lf-dev"
    langfuse_secret_key: str = "sk-lf-dev"
    langfuse_base_url: str = "http://localhost:3200"

    # LiteLLM proxy
    litellm_base_url: str = "http://localhost:4000"
    litellm_master_key: Annotated[str, Field(min_length=1)] = "sk-litellm-dev-key"
    default_model: str = "openrouter-gemini-flash"
    agent_model: str = "openrouter-mistral"
    embedding_model: Annotated[str, Field(min_length=1)] = "nomic-embed-text"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: Annotated[str, Field(min_length=1)] = "watsonx_docs"

    # OpenRouter (optional)
    openrouter_api_key: str = ""

    # API model catalog overrides (optional)
    # JSON object: {"public-model-id": "litellm-model-id", ...}
    api_models_json: str = ""
    # JSON object: {"public-model-id": "description", ...}
    api_model_descriptions_json: str = ""
    # Comma-separated public model IDs that should be routed as direct or agent modes.
    api_direct_models_csv: str = "agentguard-direct"
    api_agent_models_csv: str = "agentguard-agent,agentguard-agent-claude-haiku"

    # GitHub MCP (optional — enables GitHub tools in agent)
    github_personal_access_token: str = ""
    # SSE URL of github-mcp sidecar (set automatically in Docker; leave empty for stdio on host)
    github_mcp_url: str = "http://github-mcp:8080/mcp"

    # DeepEval judge model — defaults to Gemini Flash via OpenRouter for stable evaluation
    deepeval_model: str = "openrouter-gemini-flash"

    # RAGAS judge model — leave empty to fall back to default_model
    ragas_model: str = ""

    # Qdrant collection for watsonx corpus (separate from northstar_crm)
    watsonx_collection: str = "watsonx_docs"

    # Open WebUI — used by sync_feedback worker
    openwebui_base_url: str = "http://localhost:3001"
    openwebui_email: str = ""
    openwebui_password: str = ""

    # Opik tracing (LangChain callback)
    opik_tracing_enabled: bool = True
    opik_url_override: str = "http://localhost:5173"
    opik_project_name: str = "agentguard"
    opik_workspace: str = "default"

    # OpenTelemetry
    otel_enabled: bool = True
    otel_endpoint: str = "http://localhost:4318/v1/traces"

    # HTTP timeouts (seconds)
    # General outbound calls (Langfuse REST, workers, benchmark direct mode, etc.)
    http_timeout_seconds: Annotated[int, Field(gt=0)] = 60
    # Upstream model calls routed through LiteLLM can be slower under load.
    litellm_timeout_seconds: Annotated[int, Field(gt=0)] = 120

    # CORS — comma-separated allowed origins; "*" allows all
    # Example: CORS_ORIGINS=http://localhost:3001,https://your-domain.com
    cors_origins: str = "*"

    @field_validator(
        "langfuse_base_url",
        "litellm_base_url",
        "qdrant_url",
        "openwebui_base_url",
        "otel_endpoint",
        mode="after",
    )
    @classmethod
    def _validate_url(cls, v: str) -> str:
        if not v.startswith(_URL_SCHEMES):
            raise ValueError(f"must start with http:// or https://, got: {v!r}")
        return v


settings = Settings()
