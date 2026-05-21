from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Langfuse
    langfuse_public_key: str = "pk-lf-dev"
    langfuse_secret_key: str = "sk-lf-dev"
    langfuse_base_url: str = "http://localhost:3000"

    # LiteLLM proxy
    litellm_base_url: str = "http://localhost:4000"
    litellm_master_key: str = "sk-litellm-dev-key"
    default_model: str = "openrouter-gemini-flash"
    embedding_model: str = "nomic-embed-text"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "langfuse_docs"

    # OpenRouter (optional)
    openrouter_api_key: str = ""

    # DeepEval judge model — defaults to Gemini Flash via OpenRouter for stable evaluation
    deepeval_model: str = "openrouter-gemini-flash"


settings = Settings()
