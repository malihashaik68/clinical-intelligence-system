"""Patients, access control, consent, emergency access and the audit log.

Access rules (enforced here, used by both the API and the Streamlit app):
  1. A practitioner sees records written at THEIR OWN hospital, for patients
     registered at that hospital.
  2. Records from OTHER hospitals are visible only with an active AccessGrant for
     (patient, practitioner's hospital):
       - "consent":   patient approved with a one-time code sent to their phone (simulated), 7 days
       - "emergency": break-the-glass with a written reason, 24 hours, flagged for review
  3. The record locator (which hospitals hold records) is visible to any practitioner,
     but not the records themselves.
  4. Every view, note, question, consent and emergency access is written to the AccessLog.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func

from backend.app.db.database import SessionLocal
from backend.app.db.models import (AccessGrant, AccessLog, ClinicalRecord, ConsentRequest, Hospital,
                                   Patient, PatientRegistration, Practitioner)
from backend.app.services.security import hash_secret, verify_secret

CONSENT_DAYS = 7
EMERGENCY_HOURS = 24
OTP_MINUTES = 10
MAX_OTP_ATTEMPTS = 5


class AccessDenied(Exception):
    pass


@dataclass
class User:
    id: int
    username: str
    full_name: str
    role: str
    hospital_id: int
    hospital_name: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _age(dob: date) -> int:
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# ------------------------------------------------------------------- login
def authenticate(username: str, password: str) -> User | None:
    with SessionLocal() as db:
        p = db.query(Practitioner).filter(func.lower(Practitioner.username) == username.strip().lower()).first()
        if not p or not verify_secret(password, p.password_hash):
            return None
        hospital = db.get(Hospital, p.hospital_id)
        _log(db, p.id, None, p.hospital_id, "login", "")
        db.commit()
        return User(p.id, p.username, p.full_name, p.role, p.hospital_id, hospital.name)


def get_user(practitioner_id: int) -> User | None:
    with SessionLocal() as db:
        p = db.get(Practitioner, practitioner_id)
        if not p:
            return None
        return User(p.id, p.username, p.full_name, p.role, p.hospital_id, db.get(Hospital, p.hospital_id).name)


# --------------------------------------------------------------- audit log
def _log(db, practitioner_id, patient_id, hospital_id, action, detail):
    db.add(AccessLog(practitioner_id=practitioner_id, patient_id=patient_id, hospital_id=hospital_id,
                     action=action, detail=detail))


def access_log(user: User, patient_id: int) -> list[dict]:
    """Who accessed this patient's records. Visible to staff who can see the patient."""
    require_view(user, patient_id)
    with SessionLocal() as db:
        rows = (db.query(AccessLog, Practitioner, Hospital)
                .outerjoin(Practitioner, AccessLog.practitioner_id == Practitioner.id)
                .outerjoin(Hospital, AccessLog.hospital_id == Hospital.id)
                .filter(AccessLog.patient_id == patient_id)
                .order_by(AccessLog.created_at.desc()).limit(200).all())
        return [{"time": _aware(log.created_at).isoformat(timespec="seconds"),
                 "practitioner": prac.full_name if prac else "system",
                 "hospital": hosp.name if hosp else "",
                 "action": log.action, "detail": log.detail} for log, prac, hosp in rows]


# ------------------------------------------------------------- permissions
def _registered_hospitals(db, patient_id: int) -> set[int]:
    return {r.hospital_id for r in db.query(PatientRegistration).filter_by(patient_id=patient_id)}


def _active_grant(db, patient_id: int, hospital_id: int) -> AccessGrant | None:
    now = _now()
    grants = (db.query(AccessGrant)
              .filter_by(patient_id=patient_id, hospital_id=hospital_id, revoked=False)
              .order_by(AccessGrant.expires_at.desc()).all())
    return next((g for g in grants if _aware(g.expires_at) > now), None)


def access_status(user: User, patient_id: int) -> dict:
    """What this practitioner may see for this patient, and why."""
    with SessionLocal() as db:
        registered = user.hospital_id in _registered_hospitals(db, patient_id)
        grant = _active_grant(db, patient_id, user.hospital_id)
        return {
            "registered_here": registered,
            "own_hospital_records": registered,
            "other_hospital_records": grant is not None,
            "grant_kind": grant.kind if grant else None,
            "grant_expires": _aware(grant.expires_at).isoformat(timespec="minutes") if grant else None,
        }


def can_view(user: User, patient_id: int) -> bool:
    s = access_status(user, patient_id)
    return s["own_hospital_records"] or s["other_hospital_records"]


def require_view(user: User, patient_id: int) -> None:
    if not can_view(user, patient_id):
        raise AccessDenied("You have no access to this patient's records. Request patient consent, "
                           "or use emergency access if the patient cannot consent.")


# ----------------------------------------------------------------- patients
def _patient_dict(db, p: Patient) -> dict:
    hospitals = (db.query(Hospital.name, func.count(ClinicalRecord.id))
                 .join(ClinicalRecord, ClinicalRecord.hospital_id == Hospital.id)
                 .filter(ClinicalRecord.patient_id == p.id).group_by(Hospital.name).all())
    return {"id": p.id, "health_id": p.health_id, "full_name": p.full_name,
            "date_of_birth": p.date_of_birth.isoformat(), "age": _age(p.date_of_birth), "sex": p.sex,
            "blood_type": p.blood_type, "phone": p.phone, "emergency_contact": p.emergency_contact,
            # record locator: where records exist (not their contents)
            "records_at": {name: n for name, n in hospitals}}


def my_patients(user: User) -> list[dict]:
    with SessionLocal() as db:
        regs = db.query(PatientRegistration).filter_by(hospital_id=user.hospital_id).all()
        ids = {r.patient_id for r in regs}
        ids |= {g.patient_id for g in db.query(AccessGrant).filter_by(hospital_id=user.hospital_id, revoked=False)
                if _aware(g.expires_at) > _now()}
        return [_patient_dict(db, db.get(Patient, i)) for i in sorted(ids)]


def search_patients(user: User, health_id: str = "", name: str = "", dob: date | None = None) -> list[dict]:
    """Network patient index: returns identity + where records exist, never clinical content.
    Matching: exact health ID, or name + date of birth. Name-only matches are flagged as uncertain."""
    with SessionLocal() as db:
        q = db.query(Patient)
        if health_id.strip():
            rows = q.filter(func.upper(Patient.health_id) == health_id.strip().upper()).all()
            confidence = "exact health ID"
        elif name.strip():
            rows = q.filter(Patient.full_name.ilike(f"%{name.strip()}%")).all()
            if dob:
                rows = [r for r in rows if r.date_of_birth == dob]
                confidence = "name + date of birth"
            else:
                confidence = "name only: confirm identity before use"
        else:
            return []
        _log(db, user.id, None, user.hospital_id, "search",
             f"health_id={health_id!r} name={name!r} dob={dob}")
        db.commit()
        out = []
        for r in rows[:20]:
            d = _patient_dict(db, r)
            d.update(match=confidence, registered_here=user.hospital_id in _registered_hospitals(db, r.id))
            out.append(d)
        return out


def get_patient(user: User, patient_id: int) -> dict:
    require_view(user, patient_id)
    with SessionLocal() as db:
        return _patient_dict(db, db.get(Patient, patient_id))


def register_patient_here(user: User, patient_id: int) -> None:
    """Register an existing network patient at the practitioner's hospital (e.g. new visit at Hospital B)."""
    with SessionLocal() as db:
        if user.hospital_id not in _registered_hospitals(db, patient_id):
            n = db.query(PatientRegistration).filter_by(hospital_id=user.hospital_id).count() + 1
            db.add(PatientRegistration(patient_id=patient_id, hospital_id=user.hospital_id,
                                       local_mrn=f"H{user.hospital_id}-{n:05d}"))
            _log(db, user.id, patient_id, user.hospital_id, "register", "registered as a patient here")
            db.commit()


# -------------------------------------------------- consent & emergency
def request_consent(user: User, patient_id: int) -> str:
    """Create a one-time code 'sent' to the patient's phone. Returns the code so the demo can
    display it as a simulated SMS; a real system would send it via an SMS provider."""
    code = f"{secrets.randbelow(10**6):06d}"
    with SessionLocal() as db:
        db.add(ConsentRequest(patient_id=patient_id, hospital_id=user.hospital_id, practitioner_id=user.id,
                              code_hash=hash_secret(code), expires_at=_now() + timedelta(minutes=OTP_MINUTES)))
        _log(db, user.id, patient_id, user.hospital_id, "consent_requested", "one-time code sent to patient")
        db.commit()
    return code


def confirm_consent(user: User, patient_id: int, code: str) -> bool:
    with SessionLocal() as db:
        req = (db.query(ConsentRequest)
               .filter_by(patient_id=patient_id, hospital_id=user.hospital_id, used=False)
               .order_by(ConsentRequest.created_at.desc()).first())
        if not req or _aware(req.expires_at) < _now() or req.attempts >= MAX_OTP_ATTEMPTS:
            return False
        req.attempts += 1
        if not verify_secret(code.strip(), req.code_hash):
            _log(db, user.id, patient_id, user.hospital_id, "consent_failed", "wrong code")
            db.commit()
            return False
        req.used = True
        db.add(AccessGrant(patient_id=patient_id, hospital_id=user.hospital_id, practitioner_id=user.id,
                           kind="consent", reason="patient approved via one-time code",
                           expires_at=_now() + timedelta(days=CONSENT_DAYS)))
        _log(db, user.id, patient_id, user.hospital_id, "consent_granted", f"{CONSENT_DAYS}-day access")
        db.commit()
        return True


def emergency_access(user: User, patient_id: int, reason: str) -> None:
    """Break-the-glass: immediate access when the patient cannot consent. Requires a reason,
    lasts 24 hours and is flagged in the log for review (patient and home hospital notified)."""
    if len(reason.strip()) < 10:
        raise ValueError("Please describe the emergency (at least 10 characters).")
    with SessionLocal() as db:
        db.add(AccessGrant(patient_id=patient_id, hospital_id=user.hospital_id, practitioner_id=user.id,
                           kind="emergency", reason=reason.strip(),
                           expires_at=_now() + timedelta(hours=EMERGENCY_HOURS)))
        _log(db, user.id, patient_id, user.hospital_id, "EMERGENCY_ACCESS",
             f"break-the-glass: {reason.strip()} (patient and home hospital to be notified)")
        db.commit()


# ------------------------------------------------------------------ records
def visible_records(user: User, patient_id: int, log_action: str | None = "view_records") -> list[dict]:
    """All records this practitioner may see for the patient, newest first."""
    status = access_status(user, patient_id)
    if not (status["own_hospital_records"] or status["other_hospital_records"]):
        raise AccessDenied("No access to this patient's records.")
    with SessionLocal() as db:
        q = (db.query(ClinicalRecord, Hospital, Practitioner)
             .join(Hospital, ClinicalRecord.hospital_id == Hospital.id)
             .outerjoin(Practitioner, ClinicalRecord.practitioner_id == Practitioner.id)
             .filter(ClinicalRecord.patient_id == patient_id))
        if not status["other_hospital_records"]:
            q = q.filter(ClinicalRecord.hospital_id == user.hospital_id)
        rows = q.order_by(ClinicalRecord.visit_date.desc(), ClinicalRecord.id.desc()).all()
        if log_action:
            scope = "all hospitals" if status["other_hospital_records"] else "own hospital"
            _log(db, user.id, patient_id, user.hospital_id, log_action, f"{len(rows)} records ({scope})")
            db.commit()
        return [{
            "id": r.id,
            "visit_date": (r.visit_date or r.created_at.date()).isoformat(),
            "hospital": h.name,
            "hospital_id": h.id,
            "author": p.full_name if p else "",
            "clinical_note": r.clinical_note,
            "entities": json.loads(r.extracted_entities),
            "api_results": json.loads(r.api_results),
        } for r, h, p in rows]


def hidden_record_count(user: User, patient_id: int) -> int:
    """How many records exist at other hospitals that this practitioner cannot see yet."""
    if access_status(user, patient_id)["other_hospital_records"]:
        return 0
    with SessionLocal() as db:
        return (db.query(ClinicalRecord)
                .filter(ClinicalRecord.patient_id == patient_id,
                        ClinicalRecord.hospital_id != user.hospital_id).count())


def add_visit_note(user: User, patient_id: int, note: str, visit_date: date | None = None,
                   grounding: bool = True, literature: bool = True) -> dict:
    """Analyse a new note with the note analyser and save it to the patient's record at this hospital."""
    from backend.app.services.clinical_pipeline_service import run_clinical_pipeline_from_note

    if not note.strip():
        raise ValueError("The note is empty.")
    register_patient_here(user, patient_id)
    result = run_clinical_pipeline_from_note(note, patient_id=patient_id, hospital_id=user.hospital_id,
                                             practitioner_id=user.id, visit_date=visit_date or date.today(),
                                             grounding=grounding, literature=literature)
    with SessionLocal() as db:
        _log(db, user.id, patient_id, user.hospital_id, "add_note",
             f"record #{result['database']['record_id']}")
        db.commit()
    return result


def log_event(user: User, patient_id: int, action: str, detail: str = "") -> None:
    with SessionLocal() as db:
        _log(db, user.id, patient_id, user.hospital_id, action, detail)
        db.commit()
