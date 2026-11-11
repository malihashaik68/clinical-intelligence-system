from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.services.clinical_pipeline_service import run_clinical_pipeline_from_note

router = APIRouter(prefix="/extract", tags=["From Note Extraction"])


class ClinicalNoteRequest(BaseModel):
    clinical_note: str


@router.post("/from-note")
def extract_from_note(payload: ClinicalNoteRequest):
    return run_clinical_pipeline_from_note(payload.clinical_note)