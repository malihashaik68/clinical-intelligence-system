from fastapi import APIRouter, Query

from backend.app.services.retrieve_service import (
    get_all_clinical_records,
    get_clinical_record_by_id
)

router = APIRouter(prefix="/records", tags=["Clinical Records"])


@router.get("/")
def fetch_all_records(
    diagnosis: str | None = Query(default=None),
    symptom: str | None = Query(default=None),
    medication: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100)
):
    return get_all_clinical_records(
        diagnosis=diagnosis,
        symptom=symptom,
        medication=medication,
        skip=skip,
        limit=limit
    )


@router.get("/{record_id}")
def fetch_record_by_id(record_id: int):
    return get_clinical_record_by_id(record_id)