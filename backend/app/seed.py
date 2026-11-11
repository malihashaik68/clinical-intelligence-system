"""Synthetic demo data: two hospitals, three practitioners, four fictional patients.

Every name, ID and note is invented. Each patient demonstrates one scenario:
  * Priya Sharma: all history at City General; arrives at Riverside unconscious ->
    emergency access shows her penicillin allergy and current medications.
  * Rahul Verma: on warfarin at City General; Riverside prescribed ibuprofen ->
    after patient consent, the cross-hospital bleeding-risk interaction appears.
  * James Wilson: lisinopril 10 mg at City General vs 20 mg at Riverside, plus
    spironolactone -> dose reconciliation and high-potassium interaction alerts.
  * Maria Lopez: Riverside-only patient with a sulfa allergy.

Run:  python -m backend.app.seed  (add --reset to start from an empty database)
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from backend.app.db.database import SessionLocal, init_db
from backend.app.db.models import ClinicalRecord, Hospital, Patient, PatientRegistration, Practitioner
from backend.app.services.security import hash_secret

DEMO_PASSWORD = "demo1234"

HOSPITALS = [("City General Hospital", "Springfield"), ("Riverside Medical Center", "Riverside")]
PRACTITIONERS = [
    ("dr.rao", "Dr. Anita Rao", "Cardiologist", 0),
    ("dr.chen", "Dr. Michael Chen", "Primary care physician", 0),
    ("dr.lee", "Dr. Sarah Lee", "Emergency physician", 1),
]
PATIENTS = [
    {"health_id": "HID-4821-7730", "full_name": "Priya Sharma", "dob": date(1968, 4, 12), "sex": "F",
     "blood_type": "B+", "phone": "+1-555-0142", "emergency_contact": "Arjun Sharma (husband), +1-555-0143",
     "registered": [0],
     "visits": [
         (0, "dr.chen", 700, "Routine diabetes follow-up. History of type 2 diabetes. Allergic to penicillin (rash). "
                             "Continues metformin 500 mg twice daily. Reports mild fatigue."),
         (0, "dr.chen", 300, "Blood pressure elevated at several visits; diagnosed with hypertension. "
                             "Started lisinopril 10 mg daily. Continues metformin 500 mg twice daily."),
         (0, "dr.rao", 40, "58-year-old female with hypertension and type 2 diabetes presents with chest pain and "
                           "shortness of breath on exertion. ECG unremarkable. Started aspirin 81 mg daily and "
                           "atorvastatin 20 mg daily. Continues metformin 500 mg twice daily and lisinopril 10 mg daily."),
     ]},
    {"health_id": "HID-3390-1185", "full_name": "Rahul Verma", "dob": date(1955, 9, 3), "sex": "M",
     "blood_type": "O+", "phone": "+1-555-0177", "emergency_contact": "Neha Verma (daughter), +1-555-0178",
     "registered": [0, 1],
     "visits": [
         (0, "dr.rao", 200, "68-year-old male with atrial fibrillation on warfarin 5 mg daily. Also hypertension, "
                            "treated with amlodipine 5 mg daily. No known drug allergies."),
         (1, "dr.lee", 10, "Seen in the emergency department for knee pain and swelling after a fall. Diagnosed with "
                           "osteoarthritis. Prescribed ibuprofen 400 mg three times daily."),
     ]},
    {"health_id": "HID-7746-2210", "full_name": "James Wilson", "dob": date(1960, 11, 30), "sex": "M",
     "blood_type": "AB+", "phone": "+1-555-0191", "emergency_contact": "Linda Wilson (wife), +1-555-0192",
     "registered": [0, 1],
     "visits": [
         (0, "dr.rao", 90, "Heart failure and chronic kidney disease. Reports shortness of breath and leg swelling. "
                           "On furosemide 40 mg daily and lisinopril 10 mg daily."),
         (1, "dr.lee", 20, "Follow-up for heart failure with fatigue. Taking lisinopril 20 mg daily. "
                           "Spironolactone 25 mg daily added."),
     ]},
    {"health_id": "HID-5512-9042", "full_name": "Maria Lopez", "dob": date(1990, 2, 18), "sex": "F",
     "blood_type": "A-", "phone": "+1-555-0120", "emergency_contact": "Carlos Lopez (brother), +1-555-0121",
     "registered": [1],
     "visits": [
         (1, "dr.lee", 120, "Asthma with wheezing and cough. Allergies: sulfa drugs. Uses albuterol inhaler as needed "
                            "and fluticasone inhaler daily."),
         (1, "dr.lee", 15, "Acute bronchitis with productive cough and fever. Prescribed azithromycin 250 mg daily."),
     ]},
]


def seed_demo_data(reset: bool = False) -> bool:
    """Create the demo data if the database has no hospitals yet. Returns True if it seeded."""
    from backend.app.db.database import Base, engine
    from backend.app.services.clinical_pipeline_service import analyse_note

    if reset:
        Base.metadata.drop_all(bind=engine)
    init_db()
    with SessionLocal() as db:
        if db.query(Hospital).count():
            return False
        hospitals = [Hospital(name=n, city=c) for n, c in HOSPITALS]
        db.add_all(hospitals)
        db.flush()
        pracs = {}
        for username, name, role, h in PRACTITIONERS:
            pracs[username] = Practitioner(username=username, full_name=name, role=role,
                                           hospital_id=hospitals[h].id, password_hash=hash_secret(DEMO_PASSWORD))
            db.add(pracs[username])
        db.flush()
        for spec in PATIENTS:
            p = Patient(health_id=spec["health_id"], full_name=spec["full_name"], date_of_birth=spec["dob"],
                        sex=spec["sex"], blood_type=spec["blood_type"], phone=spec["phone"],
                        emergency_contact=spec["emergency_contact"])
            db.add(p)
            db.flush()
            for i, h in enumerate(spec["registered"]):
                db.add(PatientRegistration(patient_id=p.id, hospital_id=hospitals[h].id,
                                           local_mrn=f"H{hospitals[h].id}-{p.id:05d}"))
            for h, author, days_ago, note in spec["visits"]:
                result = analyse_note(note, grounding=False)  # fast: no external lookups for seed data
                db.add(ClinicalRecord(clinical_note=note, patient_id=p.id, hospital_id=hospitals[h].id,
                                      practitioner_id=pracs[author].id,
                                      visit_date=date.today() - timedelta(days=days_ago),
                                      extracted_entities=json.dumps(result["extracted_entities"]),
                                      api_results=json.dumps({"note": "seeded demo record"})))
        db.commit()
    return True


if __name__ == "__main__":
    print("seeded" if seed_demo_data(reset="--reset" in sys.argv) else "database already has data")
