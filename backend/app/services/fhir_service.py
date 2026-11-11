"""Export a patient's accessible history as an HL7 FHIR R4 Bundle.

FHIR is the standard hospitals use to exchange records. Exporting in this format is how
Hospital A's data would travel to Hospital B in a real health-information exchange.
Resources: Patient, AllergyIntolerance, Condition, MedicationStatement, Encounter.
"""
from __future__ import annotations

from datetime import datetime, timezone

RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"


def _rxcui_lookup(records: list[dict]) -> dict:
    """RxCUI codes found by the note analyser's RxNorm grounding, keyed by drug name."""
    codes = {}
    for r in records:
        ctx = (r.get("api_results") or {}).get("structured_context") or {}
        for m in ctx.get("medications", []):
            rx = m.get("rxnorm") or {}
            if rx.get("rxcui"):
                codes[m["input_name"].lower()] = rx["rxcui"]
    return codes


def build_fhir_bundle(patient: dict, summary: dict, records: list[dict]) -> dict:
    pid = f"patient-{patient['id']}"
    ref = {"reference": f"Patient/{pid}"}
    entries = [{"resource": {
        "resourceType": "Patient", "id": pid,
        "identifier": [{"system": "urn:demo:health-id", "value": patient["health_id"]}],
        "name": [{"text": patient["full_name"]}],
        "gender": {"F": "female", "M": "male"}.get(patient.get("sex"), "unknown"),
        "birthDate": patient["date_of_birth"],
        "telecom": [{"system": "phone", "value": patient.get("phone", "")}],
        "contact": [{"name": {"text": patient.get("emergency_contact", "")}}],
    }}]
    for i, a in enumerate(summary["allergies"], 1):
        res = {"resourceType": "AllergyIntolerance", "id": f"allergy-{i}", "patient": ref,
               "clinicalStatus": {"text": "active"}, "code": {"text": a["substance"]},
               "recordedDate": a["date"], "note": [{"text": f"Recorded at {a['hospital']}"}]}
        if a.get("reaction"):
            res["reaction"] = [{"manifestation": [{"text": a["reaction"]}]}]
        entries.append({"resource": res})
    for i, c in enumerate(summary["conditions"], 1):
        entries.append({"resource": {
            "resourceType": "Condition", "id": f"condition-{i}", "subject": ref,
            "code": {"text": c["name"]}, "onsetDateTime": c["first_seen"],
            "note": [{"text": "Recorded at " + ", ".join(c["hospitals"])}]}})
    codes = _rxcui_lookup(records)
    for i, m in enumerate(summary["current_medications"] + summary["older_medications"], 1):
        concept = {"text": m["name"]}
        if m["name"] in codes:
            concept["coding"] = [{"system": RXNORM, "code": codes[m["name"]], "display": m["name"]}]
        res = {"resourceType": "MedicationStatement", "id": f"medication-{i}", "subject": ref,
               "status": "unknown" if m.get("stale") else "active", "medicationCodeableConcept": concept,
               "effectiveDateTime": m["last_seen"], "note": [{"text": f"Last noted at {m['hospital']}"}]}
        if m.get("dosage"):
            res["dosage"] = [{"text": m["dosage"]}]
        entries.append({"resource": res})
    for r in records:
        entries.append({"resource": {
            "resourceType": "Encounter", "id": f"encounter-{r['id']}", "status": "finished", "subject": ref,
            "period": {"start": r["visit_date"]}, "serviceProvider": {"display": r["hospital"]},
            "text": {"status": "generated", "div": f"<div xmlns=\"http://www.w3.org/1999/xhtml\">{r['clinical_note']}</div>"}}})
    return {"resourceType": "Bundle", "type": "collection",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "entry": [{"fullUrl": f"urn:uuid:{e['resource']['resourceType'].lower()}-{e['resource']['id']}", **e}
                      for e in entries]}
