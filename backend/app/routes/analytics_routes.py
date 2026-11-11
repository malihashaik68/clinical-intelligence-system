from fastapi import APIRouter

from backend.app.services.analytics_service import get_analytics_summary

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary")
def analytics_summary():
    return get_analytics_summary()