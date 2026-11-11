from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.utils.data_extractors import extract_clinical_context
from backend.app.utils.note_entity_extractor import extract_entities_from_note

router = APIRouter(prefix="/extract", tags=["Extraction"])


# -------- EXISTING ROUTE --------
@router.post("/context")
def extract_context(payload: dict):
    return extract_clinical_context(payload)


# -------- NEW ROUTE --------
class ClinicalNoteRequest(BaseModel):
    clinical_note: str


@router.post("/from-note")
def extract_from_note(payload: ClinicalNoteRequest):
    extracted = extract_entities_from_note(payload.clinical_note)
    result = extract_clinical_context(extracted)

    return {
        "extracted_entities": extracted,
        "api_results": result
    }