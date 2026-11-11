from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.app.routes.deps import current_user
from backend.app.services import patient_service as ps
from backend.app.services.emergency_card import render_card
from backend.app.services.fhir_service import build_fhir_bundle
from backend.app.services.qa_service import answer_question
from backend.app.services.summary_service import build_summary

router = APIRouter(prefix="/patients", tags=["Patients"])


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ps.AccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _context(user, patient_id, action="view_records"):
    patient = _guard(ps.get_patient, user, patient_id)
    records = _guard(ps.visible_records, user, patient_id, log_action=action)
    return patient, records, build_summary(records)


class NoteRequest(BaseModel):
    clinical_note: str
    visit_date: date | None = None
    literature: bool = True


class CodeRequest(BaseModel):
    code: str


class ReasonRequest(BaseModel):
    reason: str


class QuestionRequest(BaseModel):
    question: str


@router.get("/")
def my_patients(user=Depends(current_user)):
    return ps.my_patients(user)


@router.get("/search")
def search(health_id: str = "", name: str = "", dob: date | None = None, user=Depends(current_user)):
    return ps.search_patients(user, health_id=health_id, name=name, dob=dob)


@router.get("/{patient_id}/summary")
def summary(patient_id: int, user=Depends(current_user)):
    patient, records, s = _context(user, patient_id)
    return {"patient": patient, "access": ps.access_status(user, patient_id),
            "hidden_records_at_other_hospitals": ps.hidden_record_count(user, patient_id),
            "summary": s, "records": records}


@router.post("/{patient_id}/notes")
def add_note(patient_id: int, payload: NoteRequest, user=Depends(current_user)):
    return _guard(ps.add_visit_note, user, patient_id, payload.clinical_note, payload.visit_date,
                  literature=payload.literature)


@router.post("/{patient_id}/consent/request")
def consent_request(patient_id: int, user=Depends(current_user)):
    code = ps.request_consent(user, patient_id)
    # Demo only: a real system sends this code to the patient's phone and never returns it.
    return {"message": "One-time code sent to the patient's phone (simulated).", "simulated_sms_code": code}


@router.post("/{patient_id}/consent/confirm")
def consent_confirm(patient_id: int, payload: CodeRequest, user=Depends(current_user)):
    if not ps.confirm_consent(user, patient_id, payload.code):
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    return {"granted": True, "access": ps.access_status(user, patient_id)}


@router.post("/{patient_id}/emergency-access")
def emergency(patient_id: int, payload: ReasonRequest, user=Depends(current_user)):
    _guard(ps.emergency_access, user, patient_id, payload.reason)
    return {"granted": True, "access": ps.access_status(user, patient_id)}


@router.post("/{patient_id}/ask")
def ask(patient_id: int, payload: QuestionRequest, user=Depends(current_user)):
    patient, records, s = _context(user, patient_id, action=None)
    ps.log_event(user, patient_id, "ask", payload.question[:200])
    return answer_question(payload.question, s, records, patient)


@router.get("/{patient_id}/access-log")
def log(patient_id: int, user=Depends(current_user)):
    return _guard(ps.access_log, user, patient_id)


@router.get("/{patient_id}/fhir")
def fhir(patient_id: int, user=Depends(current_user)):
    patient, records, s = _context(user, patient_id, action="export_fhir")
    return build_fhir_bundle(patient, s, records)


@router.get("/{patient_id}/emergency-card", responses={200: {"content": {"image/png": {}}}})
def card(patient_id: int, user=Depends(current_user)):
    patient, records, s = _context(user, patient_id, action="emergency_card")
    return Response(render_card(patient, s), media_type="image/png")
