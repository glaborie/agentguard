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
    qdrant_collection: Annotated[str, Field(min_length=1)] = "northstar_crm"

    # OpenRouter (optional)
    openrouter_api_key: str = ""

    # GitHub MCP (optional — enables GitHub tools in agent)
    github_personal_access_token: str = ""

    # DeepEval judge model — defaults to Gemini Flash via OpenRouter for stable evaluation
    deepeval_model: str = "openrouter-gemini-flash"

    # Open WebUI — used by sync_feedback worker
    openwebui_base_url: str = "http://localhost:3001"
    openwebui_email: str = ""
    openwebui_password: str = ""

    # OpenTelemetry
    otel_enabled: bool = True
    otel_endpoint: str = "http://localhost:4318/v1/traces"

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
