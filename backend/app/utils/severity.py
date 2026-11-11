"""Rule-based severity flag for a structured clinical note.

Deliberately simple and transparent: every flag lists the rule that fired, so a
clinician can see why a note was flagged. It is a triage aid, not a diagnosis.
"""

RED_FLAG_SYMPTOMS = {
    "chest pain": "chest pain can indicate a cardiac emergency",
    "shortness of breath": "breathing difficulty",
    "confusion": "altered mental status",
    "syncope": "loss of consciousness",
    "fainting": "loss of consciousness",
    "seizure": "seizure",
    "severe bleeding": "severe bleeding",
}
WARNING_SYMPTOMS = {
    "dizziness": "dizziness (fall / cardiovascular risk)",
    "vomiting": "vomiting (dehydration risk)",
    "leg swelling": "leg swelling (fluid overload / clot risk)",
    "edema": "edema (fluid overload)",
    "abdominal pain": "abdominal pain",
}
HIGH_RISK_DIAGNOSES = {"heart failure", "pneumonia", "chronic kidney disease", "covid-19"}
CARDIAC_RISK_DIAGNOSES = {"hypertension", "diabetes", "type 2 diabetes", "heart failure"}


def assess_severity(entities: dict) -> dict:
    symptoms = {s.lower() for s in entities.get("symptoms", [])}
    diagnoses = {d.lower() for d in entities.get("diagnoses", [])}
    medications = entities.get("medications", [])

    high, medium = [], []
    for term, why in RED_FLAG_SYMPTOMS.items():
        if term in symptoms:
            high.append(f"{term}: {why}")
    if "chest pain" in symptoms and diagnoses & CARDIAC_RISK_DIAGNOSES:
        high.append("chest pain with cardiac risk factors ("
                    + ", ".join(sorted(diagnoses & CARDIAC_RISK_DIAGNOSES)) + ")")
    if "fever" in symptoms and "shortness of breath" in symptoms:
        high.append("fever with breathing difficulty")

    for term, why in WARNING_SYMPTOMS.items():
        if term in symptoms:
            medium.append(why)
    for d in sorted(diagnoses & HIGH_RISK_DIAGNOSES):
        medium.append(f"high-risk condition: {d}")
    if "fever" in symptoms and "cough" in symptoms:
        medium.append("fever with cough (possible infection)")
    if len(diagnoses) >= 2:
        medium.append(f"{len(diagnoses)} co-existing conditions")
    if len(medications) >= 5:
        medium.append(f"polypharmacy ({len(medications)} medications)")

    level = "high" if high else "medium" if medium else "low"
    return {"level": level, "reasons": high + medium}
