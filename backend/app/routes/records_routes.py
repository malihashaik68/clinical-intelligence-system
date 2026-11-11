from fastapi import APIRouter

from backend.app.services.retrieve_service import get_all_clinical_records

router = APIRouter(prefix="/records", tags=["Clinical Records"])


@router.get("/")
def fetch_all_records():
    return get_all_clinical_records()