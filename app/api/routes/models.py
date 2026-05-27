from fastapi import APIRouter

from app.api.services import models_service

router = APIRouter()


@router.get("/v1/models")
def list_models():
    return models_service.get_model_list()
