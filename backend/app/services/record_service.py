import json
import numpy as np

from backend.app.db.database import SessionLocal
from backend.app.db.models import ClinicalRecord


def make_json_serializable(obj):
    if isinstance(obj, dict):
        return {key: make_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, tuple):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return obj


def save_clinical_record(clinical_note: str, extracted_entities: dict, api_results: dict):
    db = SessionLocal()

    try:
        safe_extracted_entities = make_json_serializable(extracted_entities)
        safe_api_results = make_json_serializable(api_results)

        record = ClinicalRecord(
            clinical_note=clinical_note,
            extracted_entities=json.dumps(safe_extracted_entities),
            api_results=json.dumps(safe_api_results)
        )

        db.add(record)
        db.commit()
        db.refresh(record)

        return {
            "message": "Record saved successfully",
            "record_id": record.id
        }

    finally:
        db.close()