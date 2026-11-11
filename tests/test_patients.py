"""Patient history, access control, consent, emergency access and safety alerts.

Uses the synthetic seed data. The BERT model is replaced by a simple stand-in so the
tests run in seconds without downloading models (the real model is covered elsewhere)."""
import os
import re

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_clinical.db")

import pytest

from backend.app.services import clinical_pipeline_service as pipeline
from backend.app.services import patient_service as ps
from backend.app.services.summary_service import build_summary, safety_alerts
from backend.app.utils.allergy_extractor import extract_allergies
from backend.app.utils.severity import assess_severity

DRUGS = ["metformin", "lisinopril", "aspirin", "atorvastatin", "warfarin", "amlodipine", "ibuprofen",
         "furosemide", "spironolactone", "albuterol", "fluticasone", "azithromycin", "amoxicillin"]
CONDITIONS = ["type 2 diabetes", "hypertension", "atrial fibrillation", "osteoarthritis", "heart failure",
              "chronic kidney disease", "asthma", "acute bronchitis"]


def fake_analyse(note, grounding=True, literature=True):
    low = note.lower()
    details = []
    for d in DRUGS:
        m = re.search(rf"\b{d}\b(?: (\d+ mg(?: (?:daily|twice daily|three times daily))?))?", low)
        if m:
            details.append({"name": d, "dosage": m.group(1)})
    entities = {"medications": [d["name"] for d in details], "medication_details": details,
                "diagnoses": [c for c in CONDITIONS if c in low], "symptoms": [], "raw_entities": []}
    entities.update(extract_allergies(note))
    entities["severity"] = assess_severity(entities)
    return {"extracted_entities": entities, "api_results": {"note": "test"}, "severity": entities["severity"]}


@pytest.fixture(scope="module", autouse=True)
def seeded():
    mp = pytest.MonkeyPatch()
    mp.setattr(pipeline, "analyse_note", fake_analyse)
    from backend.app.seed import seed_demo_data
    seed_demo_data(reset=True)
    yield
    mp.undo()


def login(name):
    user = ps.authenticate(name, "demo1234")
    assert user is not None
    return user


def pid(user, health_id):
    return ps.search_patients(user, health_id=health_id)[0]["id"]


PRIYA, RAHUL, JAMES, MARIA = "HID-4821-7730", "HID-3390-1185", "HID-7746-2210", "HID-5512-9042"


def test_login_requires_correct_password():
    assert ps.authenticate("dr.lee", "wrong") is None
    assert login("DR.LEE").hospital_name == "Riverside Medical Center"


def test_practitioner_sees_only_own_hospital_patients():
    assert {p["full_name"] for p in ps.my_patients(login("dr.rao"))} == {"Priya Sharma", "Rahul Verma", "James Wilson"}
    assert {p["full_name"] for p in ps.my_patients(login("dr.lee"))} == {"Rahul Verma", "James Wilson", "Maria Lopez"}


def test_search_returns_identity_and_record_locator_but_no_clinical_data():
    hit = ps.search_patients(login("dr.lee"), health_id=PRIYA)[0]
    assert hit["records_at"] == {"City General Hospital": 3}
    assert "entities" not in hit and "clinical_note" not in hit
    name_only = ps.search_patients(login("dr.lee"), name="priya")[0]
    assert "confirm identity" in name_only["match"]


def test_other_hospital_cannot_read_records_without_grant():
    lee = login("dr.lee")
    with pytest.raises(ps.AccessDenied):
        ps.visible_records(lee, pid(lee, PRIYA))


def test_own_hospital_records_only_until_consent():
    lee = login("dr.lee")
    rahul = pid(lee, RAHUL)
    own = ps.visible_records(lee, rahul)
    assert {r["hospital"] for r in own} == {"Riverside Medical Center"}
    assert ps.hidden_record_count(lee, rahul) == 1
    assert safety_alerts(build_summary(own)) == []          # warfarin is invisible: no alert yet

    code = ps.request_consent(lee, rahul)
    assert not ps.confirm_consent(lee, rahul, "999999" if code != "999999" else "111111")
    assert ps.confirm_consent(lee, rahul, code)
    assert not ps.confirm_consent(lee, rahul, code)          # one-time code
    combined = build_summary(ps.visible_records(lee, rahul))
    assert combined["hospitals"] == ["City General Hospital", "Riverside Medical Center"]
    assert any(a["type"] == "interaction" and "warfarin" in a["message"] and a["severity"] == "high"
               for a in combined["alerts"])


def test_emergency_access_requires_reason_and_is_logged():
    lee = login("dr.lee")
    priya = pid(lee, PRIYA)
    with pytest.raises(ValueError):
        ps.emergency_access(lee, priya, "help")
    ps.emergency_access(lee, priya, "Unconscious after collapse, no history available")
    summary = build_summary(ps.visible_records(lee, priya))
    assert [a["substance"] for a in summary["allergies"]] == ["penicillin"]
    assert summary["allergies"][0]["reaction"] == "rash"
    assert {m["name"] for m in summary["current_medications"]} == {"metformin", "lisinopril", "aspirin", "atorvastatin"}
    log = ps.access_log(login("dr.rao"), priya)               # home hospital sees the emergency access
    assert any(e["action"] == "EMERGENCY_ACCESS" and e["practitioner"] == "Dr. Sarah Lee" for e in log)


def test_new_prescription_triggers_allergy_alert(monkeypatch):
    lee = login("dr.lee")
    priya = pid(lee, PRIYA)
    ps.add_visit_note(lee, priya, "Fever and cough. Prescribed amoxicillin 500 mg three times daily.")
    alerts = build_summary(ps.visible_records(lee, priya))["alerts"]
    assert any(a["type"] == "allergy" and "amoxicillin" in a["message"] and "penicillin" in a["message"]
               for a in alerts)


def test_reconciliation_and_interaction_for_james():
    lee = login("dr.lee")
    james = pid(lee, JAMES)
    ps.request_consent(lee, james)
    code = ps.request_consent(lee, james)                    # newest code is the valid one
    assert ps.confirm_consent(lee, james, code)
    alerts = build_summary(ps.visible_records(lee, james))["alerts"]
    types = {a["type"] for a in alerts}
    assert "reconciliation" in types and "interaction" in types
    rec = next(a for a in alerts if a["type"] == "reconciliation")
    assert "10 mg" in rec["message"] and "20 mg" in rec["message"]


def test_summary_merges_conditions_and_flags_old_medications():
    records = [
        {"id": 1, "visit_date": "2020-01-01", "hospital": "A", "clinical_note": "x",
         "entities": {"medication_details": [{"name": "naproxen", "dosage": "250 mg"}], "diagnoses": ["diabetes"]}},
        {"id": 2, "visit_date": "2099-01-01", "hospital": "A", "clinical_note": "y",
         "entities": {"medication_details": [], "diagnoses": ["type 2 diabetes"]}},
    ]
    s = build_summary(records)
    assert [c["name"] for c in s["conditions"]] == ["type 2 diabetes"]
    assert s["current_medications"] == [] and s["older_medications"][0]["name"] == "naproxen"


@pytest.mark.parametrize("note,expected", [
    ("Allergic to penicillin (rash).", [("penicillin", "rash")]),
    ("Allergies: sulfa drugs, latex. Cough.", [("sulfa drugs", None), ("latex", None)]),
    ("Known penicillin allergy and is on lisinopril.", [("penicillin", None)]),
    ("Patient reports allergy to aspirin and ibuprofen with hives.", [("aspirin", None), ("ibuprofen", None)]),
])
def test_allergy_extraction(note, expected):
    assert [(a["substance"], a["reaction"]) for a in extract_allergies(note)["allergies"]] == expected


def test_no_known_allergies():
    assert extract_allergies("NKDA. On amlodipine.")["no_known_allergies"] is True


# ------------------------------------------------------------ patient Q&A
from backend.app.services import qa_service as qa


def _priya_context():
    rao = login("dr.rao")
    p = ps.get_patient(rao, pid(rao, PRIYA))
    records = ps.visible_records(rao, p["id"])
    return build_summary(records), records, p


def test_qa_direct_answers_cite_sources():
    s, recs, p = _priya_context()
    a = qa.answer_question("Any allergies?", s, recs, p, use_llm=False)
    assert a["method"] == "summary" and "penicillin (rash)" in a["answer"] and "City General" in a["answer"]
    assert "aspirin" in qa.answer_question("Is she on blood thinners?", s, recs, p)["answer"]
    assert "Yes: metformin" in qa.answer_question("Is she on metformin?", s, recs, p)["answer"]
    assert "No record of warfarin" in qa.answer_question("Is she on warfarin?", s, recs, p)["answer"]
    assert qa.answer_question("What is her blood type?", s, recs, p)["answer"] == "Blood type: B+."


def test_qa_safety_check_for_proposed_drug():
    s, recs, p = _priya_context()
    a = qa.answer_question("Can I give amoxicillin?", s, recs, p)
    assert a["method"] == "safety check" and "penicillin" in a["answer"]
    a = qa.answer_question("Is it safe to prescribe warfarin?", s, recs, p)
    assert "aspirin" in a["answer"] and "bleeding" in a["answer"]       # interaction with current aspirin


def test_qa_never_invents_undocumented_facts(monkeypatch):
    s, recs, p = _priya_context()
    monkeypatch.setattr(qa, "find_evidence", lambda q, r, top_k=4: [])
    a = qa.answer_question("Does she smoke?", s, recs, p, use_llm=True)
    assert a["answer"].startswith("Not documented")


def test_qa_why_question_without_stated_reason(monkeypatch):
    s, recs, p = _priya_context()
    ev = [{"record_id": 3, "text": "Started aspirin 81 mg daily and atorvastatin 20 mg daily.", "source": "City General"}]
    monkeypatch.setattr(qa, "find_evidence", lambda q, r, top_k=4: ev)
    a = qa.answer_question("Why was she started on aspirin?", s, recs, p, use_llm=True)
    assert "does not state the reason" in a["answer"] and a["evidence"] == ev


def test_qa_rejects_llm_answer_that_adds_facts(monkeypatch):
    s, recs, p = _priya_context()
    ev = [{"record_id": 9, "text": "Heart failure and chronic kidney disease.", "source": "City General, 2026-08-13"}]
    monkeypatch.setattr(qa, "find_evidence", lambda q, r, top_k=4: ev)
    monkeypatch.setattr(qa, "_llm_answer", lambda q, e: "He is treated with diuretics and ACE inhibitors.")
    assert qa.answer_question("How is it treated?", s, recs, p, use_llm=True)["method"] == "retrieval"
    monkeypatch.setattr(qa, "_llm_answer", lambda q, e: "He has heart failure and chronic kidney disease [R9].")
    assert qa.answer_question("What conditions are noted?", s, recs, p, use_llm=True)["method"] in ("summary", "local LLM")
    assert qa.grounded("He has heart failure and chronic kidney disease.", ev, recs)
    assert not qa.grounded("Started furosemide 80 mg.", ev, recs)
