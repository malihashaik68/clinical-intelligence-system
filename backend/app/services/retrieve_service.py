import json

from backend.app.db.database import SessionLocal
from backend.app.db.models import ClinicalRecord


def format_record(record):
    return {
        "id": record.id,
        "clinical_note": record.clinical_note,
        "extracted_entities": json.loads(record.extracted_entities),
        "api_results": json.loads(record.api_results),
        "created_at": record.created_at.isoformat() if getattr(record, "created_at", None) else None
    }


def get_all_clinical_records(
    diagnosis: str = None,
    symptom: str = None,
    medication: str = None,
    skip: int = 0,
    limit: int = 20
):
    db = SessionLocal()

    try:
        query = db.query(ClinicalRecord)

        if hasattr(ClinicalRecord, "created_at"):
            query = query.order_by(ClinicalRecord.created_at.desc())

        if diagnosis:
            query = query.filter(ClinicalRecord.extracted_entities.contains(diagnosis))
        if symptom:
            query = query.filter(ClinicalRecord.extracted_entities.contains(symptom))
        if medication:
            query = query.filter(ClinicalRecord.extracted_entities.contains(medication))

        total = query.count()
        records = query.offset(skip).limit(limit).all()

        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "records": [format_record(record) for record in records]
        }

    finally:
        db.close()


def get_clinical_record_by_id(record_id: int):
    db = SessionLocal()

    try:
        record = db.query(ClinicalRecord).filter(ClinicalRecord.id == record_id).first()

        if not record:
            return {"error": f"Record {record_id} not found"}

        return format_record(record)

    finally:
        db.close()