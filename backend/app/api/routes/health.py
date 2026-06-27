from fastapi import APIRouter

from app.core.config import SERVICE_NAME

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}
