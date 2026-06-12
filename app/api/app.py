import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routes import chat, config, health, models, retrieval, webhook
from app.core.config import settings
from app.telemetry import init_telemetry

logger = logging.getLogger(__name__)


async def _warmup_bm25() -> None:
    from app.core.feature_flags import get_flags
    if not get_flags().get("hybrid_search_enabled", True):
        return
    try:
        from qdrant_client import QdrantClient
        from app.rag.bm25_index import build_or_load
        client = QdrantClient(url=settings.qdrant_url, timeout=30)
        await asyncio.get_event_loop().run_in_executor(
            None, build_or_load, client, settings.qdrant_collection
        )
        logger.info("BM25 index warm-up complete")
    except Exception as exc:
        logger.warning("BM25 warm-up skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init_telemetry(app)
    await _warmup_bm25()
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="AgentGuard RAG API", lifespan=lifespan)
    cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health.router)
    application.include_router(models.router)
    application.include_router(webhook.router)
    application.include_router(chat.router)
    application.include_router(config.router)
    application.include_router(retrieval.router)
    Instrumentator().instrument(application).expose(application, endpoint="/metrics")
    return application


app = create_app()
