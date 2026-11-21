from fastapi import APIRouter
from app.core.config import settings
from app.services.groq_service import get_quota_status

router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "ai_configured": bool(settings.groq_api_key),
    }


@router.get("/quota")
def quota():
    return get_quota_status()
