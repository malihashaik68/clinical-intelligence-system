from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/")
def health_check():
    return {
        "status": "ok",
        "service": "Clinical Intelligence Backend",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }