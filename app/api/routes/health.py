from fastapi import APIRouter
from fastapi.responses import Response

from app.api.services import health_service

router = APIRouter()


@router.get("/health")
async def health(response: Response) -> dict:
    checks, all_ok = await health_service.check_all()
    if not all_ok:
        response.status_code = 503
    return {"status": "ok" if all_ok else "degraded", "checks": checks}
