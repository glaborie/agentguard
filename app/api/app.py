from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, health, models, webhook
from app.core.config import settings
from app.telemetry import init_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_telemetry(app)
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
    return application


app = create_app()
