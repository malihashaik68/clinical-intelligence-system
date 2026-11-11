from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

from backend.app.utils.data_extractors import extract_clinical_context

router = APIRouter(prefix="/extract", tags=["Extraction"])


class ClinicalExtractionRequest(BaseModel):
    clinical_note: Optional[str] = ""
    medications: List[str] = []
    symptoms: List[str] = []
    diagnoses: List[str] = []


@router.post("/context")
def extract_context(payload: ClinicalExtractionRequest):
    data = {
        "clinical_note": payload.clinical_note,
        "medications": payload.medications,
        "symptoms": payload.symptoms,
        "diagnoses": payload.diagnoses,
    }
    return extract_clinical_context(data)