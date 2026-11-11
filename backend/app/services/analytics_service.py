import json
from collections import Counter

from backend.app.db.database import SessionLocal
from backend.app.db.models import ClinicalRecord


def get_analytics_summary():
    db = SessionLocal()

    try:
        records = db.query(ClinicalRecord).filter(ClinicalRecord.patient_id.is_(None)).all()

        diagnosis_counter = Counter()
        symptom_counter = Counter()
        medication_counter = Counter()
        severity_counter = Counter()

        for record in records:
            extracted = json.loads(record.extracted_entities)

            for diagnosis in extracted.get("diagnoses", []):
                diagnosis_counter[diagnosis] += 1

            for symptom in extracted.get("symptoms", []):
                symptom_counter[symptom] += 1

            for medication in extracted.get("medications", []):
                medication_counter[medication] += 1

            severity_counter[(extracted.get("severity") or {}).get("level", "unknown")] += 1

        return {
            "total_records": len(records),
            "top_diagnoses": diagnosis_counter.most_common(5),
            "top_symptoms": symptom_counter.most_common(5),
            "top_medications": medication_counter.most_common(5),
            "severity_counts": dict(severity_counter),
        }

    finally:
        db.close()