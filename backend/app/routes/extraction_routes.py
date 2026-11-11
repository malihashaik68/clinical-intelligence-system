from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.utils.data_extractors import extract_clinical_context
from backend.app.utils.note_entity_extractor import extract_entities_from_note

router = APIRouter(prefix="/extract", tags=["Extraction"])


@router.post("/context")
def extract_context(payload: dict):
    return extract_clinical_context(payload)


class ClinicalNoteRequest(BaseModel):
    clinical_note: str


# Lightweight keyword baseline (no model download). The BERT pipeline lives at
# POST /extract/from-note (from_note_routes.py).
@router.post("/from-note-keywords")
def extract_from_note_keywords(payload: ClinicalNoteRequest):
    extracted = extract_entities_from_note(payload.clinical_note)
    result = extract_clinical_context(extracted)

    return {
        "extracted_entities": extracted,
        "api_results": result
    }