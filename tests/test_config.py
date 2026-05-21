"""Tests for app.config.Settings.

Verifies defaults and env var override behavior.
"""

import os

import pytest


class TestSettingsDefaults:
    def test_default_values(self, monkeypatch):
        # Clear any env vars that could override the hard-coded defaults
        for key in ("DEFAULT_MODEL", "EMBEDDING_MODEL", "LANGFUSE_PUBLIC_KEY",
                    "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL", "LITELLM_BASE_URL",
                    "LITELLM_MASTER_KEY", "QDRANT_URL", "QDRANT_COLLECTION"):
            monkeypatch.delenv(key, raising=False)

        from app.config import Settings

        s = Settings(_env_file=None)
        assert s.langfuse_public_key == "pk-lf-dev"
        assert s.langfuse_secret_key == "sk-lf-dev"
        assert s.langfuse_base_url == "http://localhost:3000"
        assert s.litellm_base_url == "http://localhost:4000"
        assert s.litellm_master_key == "sk-litellm-dev-key"
        assert s.default_model == "openrouter-gemini-flash"
        assert s.embedding_model == "nomic-embed-text"
        assert s.qdrant_url == "http://localhost:6333"
        assert s.qdrant_collection == "langfuse_docs"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_MODEL", "openrouter-mistral")
        monkeypatch.setenv("QDRANT_COLLECTION", "custom_collection")

        from app.config import Settings

        s = Settings(_env_file=None)
        assert s.default_model == "openrouter-mistral"
        assert s.qdrant_collection == "custom_collection"

    def test_extra_env_vars_ignored(self, monkeypatch):
        monkeypatch.setenv("SOME_RANDOM_VAR", "value")

        from app.config import Settings

        s = Settings(_env_file=None)
        assert not hasattr(s, "some_random_var")
