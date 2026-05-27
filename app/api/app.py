from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, health, models, webhook
from app.telemetry import init_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_telemetry(app)
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="AgentGuard RAG API", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health.router)
    application.include_router(models.router)
    application.include_router(webhook.router)
    application.include_router(chat.router)
    return application


app = create_app()
