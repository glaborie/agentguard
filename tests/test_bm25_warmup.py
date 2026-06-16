"""Unit tests for BM25 warm-up in FastAPI lifespan."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_warmup_skipped_when_hybrid_disabled():
    flags = {"hybrid_search_enabled": False}
    with patch("app.core.feature_flags.get_flags", return_value=flags):
        from app.api.app import _warmup_bm25
        # Should return immediately, no QdrantClient instantiated
        with patch("qdrant_client.QdrantClient", create=True) as mock_client:
            await _warmup_bm25()
            mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_warmup_runs_when_hybrid_enabled():
    flags = {"hybrid_search_enabled": True}
    mock_retriever = MagicMock()
    with (
        patch("app.core.feature_flags.get_flags", return_value=flags),
        patch("app.core.config.settings") as mock_settings,
        patch("qdrant_client.QdrantClient", create=True),
        patch("app.rag.bm25_index.build_or_load", return_value=mock_retriever) as mock_build,
    ):
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.rag_collection = "test_col"
        from app.api.app import _warmup_bm25
        await _warmup_bm25()
        mock_build.assert_called_once()


@pytest.mark.asyncio
async def test_warmup_survives_qdrant_unreachable():
    flags = {"hybrid_search_enabled": True}
    with (
        patch("app.core.feature_flags.get_flags", return_value=flags),
        patch("app.core.config.settings") as mock_settings,
        patch("qdrant_client.QdrantClient", create=True, side_effect=ConnectionError("unreachable")),
    ):
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.rag_collection = "test_col"
        from app.api.app import _warmup_bm25
        # Must not raise — startup must not be blocked
        await _warmup_bm25()


@pytest.mark.asyncio
async def test_warmup_survives_empty_collection():
    flags = {"hybrid_search_enabled": True}
    with (
        patch("app.core.feature_flags.get_flags", return_value=flags),
        patch("app.core.config.settings") as mock_settings,
        patch("qdrant_client.QdrantClient", create=True),
        patch("app.rag.bm25_index.build_or_load", side_effect=Exception("collection empty")),
    ):
        mock_settings.qdrant_url = "http://localhost:6333"
        mock_settings.rag_collection = "test_col"
        from app.api.app import _warmup_bm25
        await _warmup_bm25()
