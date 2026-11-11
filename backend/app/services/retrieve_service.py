import json

from backend.app.db.database import SessionLocal
from backend.app.db.models import ClinicalRecord


def get_all_clinical_records():
    db = SessionLocal()

    try:
        records = db.query(ClinicalRecord).all()

        output = []
        for record in records:
            output.append({
                "id": record.id,
                "clinical_note": record.clinical_note,
                "extracted_entities": json.loads(record.extracted_entities),
                "api_results": json.loads(record.api_results),
            })

        return output

    finally:
        db.close()