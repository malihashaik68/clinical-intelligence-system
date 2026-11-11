import re
from functools import lru_cache

MODEL_NAME = "d4data/biomedical-ner-all"


@lru_cache(maxsize=1)
def get_ner_pipeline():
    """Load the biomedical NER model once, on first use (downloads ~260 MB the first time)."""
    from transformers import pipeline

    return pipeline("token-classification", model=MODEL_NAME, aggregation_strategy="simple")

KNOWN_DIAGNOSES = {
    "hypertension",
    "diabetes",
    "asthma",
    "anemia",
    "pneumonia",
    "depression",
    "migraine",
    "heart failure",
    "chronic kidney disease",
    "covid-19",
}

KNOWN_SYMPTOMS = {
    "fatigue",
    "fever",
    "cough",
    "headache",
    "dizziness",
    "chest pain",
    "shortness of breath",
    "nausea",
    "vomiting",
    "abdominal pain",
    "leg swelling",
    "swelling",
    "edema",
}

KNOWN_MEDICATIONS = {
    "metformin",
    "aspirin",
    "ibuprofen",
    "paracetamol",
    "acetaminophen",
    "lisinopril",
    "amlodipine",
    "atorvastatin",
    "insulin",
    "omeprazole",
}


def normalize_text(text: str) -> str:
    return " ".join(text.lower().split()).strip(".,;:()[]{}\"'")


def unique_keep_order(items):
    seen = set()
    output = []

    for item in items:
        key = normalize_text(item)
        if key and key not in seen:
            seen.add(key)
            output.append(item)

    return output


def expand_medication_span(clinical_note: str, start: int, end: int) -> str:
    """
    Expand a partial medication token like 'met' to 'metformin'
    by growing left/right through valid medication characters.
    """
    if start is None or end is None:
        return ""

    n = len(clinical_note)
    left = start
    right = end

    valid_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/")

    while left > 0 and clinical_note[left - 1] in valid_chars:
        left -= 1

    while right < n and clinical_note[right] in valid_chars:
        right += 1

    return clinical_note[left:right].strip()


def clean_entity_text(clinical_note: str, item: dict) -> str:
    start = item.get("start")
    end = item.get("end")
    entity_group = item.get("entity_group", "").strip().lower()

    if entity_group == "medication" and start is not None and end is not None:
        expanded = expand_medication_span(clinical_note, start, end)
        if expanded:
            return expanded

    if start is not None and end is not None and 0 <= start < end <= len(clinical_note):
        return clinical_note[start:end].strip()

    return item.get("word", "").strip()


# Generic words the model sometimes tags as a medication ("current medications include ...").
GENERIC_MEDICATION_WORDS = {"medication", "medications", "meds", "drug", "drugs", "medicine", "medicines"}
DIAGNOSIS_GROUPS = {"disease_disorder", "disease", "diagnosis", "history"}
SYMPTOM_GROUPS = {"sign_symptom", "symptom"}


def merge_word_pieces(clinical_note: str, results: list) -> list:
    """Join fragments of one word that the model returned separately,
    e.g. 'di' + 'zziness' -> 'dizziness' (same label, no gap between them)."""
    merged = []
    for item in sorted(results, key=lambda r: (r.get("start") or 0)):
        item = dict(item)
        if merged:
            prev = merged[-1]
            touching = prev.get("end") == item.get("start")
            inside_word = (item.get("start") or 0) > 0 and clinical_note[item["start"] - 1].isalnum() \
                and clinical_note[item["start"]].isalnum()
            if touching and inside_word:
                prev["end"] = item["end"]
                prev["word"] = clinical_note[prev["start"]:prev["end"]]
                prev["score"] = min(float(prev["score"]), float(item["score"]))
                continue
        merged.append(item)
    return merged


def attach_body_parts(clinical_note: str, results: list) -> list:
    """'chest' (Biological_structure) right before 'pain' (Sign_symptom) -> 'chest pain'."""
    out = []
    for item in results:
        group = item.get("entity_group", "").lower()
        if out and group in SYMPTOM_GROUPS:
            prev = out[-1]
            gap = clinical_note[prev["end"]:item["start"]] if prev.get("end") is not None else "x"
            if prev.get("entity_group", "").lower() == "biological_structure" and gap.strip() == "":
                out[-1] = {**item, "start": prev["start"],
                           "word": clinical_note[prev["start"]:item["end"]],
                           "score": min(float(prev["score"]), float(item["score"]))}
                continue
        out.append(item)
    return out


_UNIT = re.compile(r"^\s*(mg|mcg|µg|g|ml|mL|units?|iu|IU|%)\b")


def complete_dosage(clinical_note: str, item: dict) -> dict:
    """'81' followed by ' mg' in the note -> '81 mg'."""
    m = _UNIT.match(clinical_note[item["end"]:])
    if m:
        item = {**item, "end": item["end"] + m.end(),
                "word": clinical_note[item["start"]:item["end"] + m.end()]}
    return item


def dictionary_matches(clinical_note: str, terms: set, already_found: list) -> list:
    """Known terms written in the note that the model missed (whole-word, case-insensitive)."""
    found = {normalize_text(x) for x in already_found}
    hits = []
    for term in sorted(terms, key=len, reverse=True):
        if term in found or any(term in f for f in found if f):
            continue
        if re.search(rf"\b{re.escape(term)}\b", clinical_note, re.I):
            hits.append(term)
            found.add(term)
    return hits


def structure_entities(clinical_note: str, results: list) -> dict:
    """Turn raw NER output into medications (with dosage), symptoms and diagnoses."""
    results = attach_body_parts(clinical_note, merge_word_pieces(clinical_note, results))

    medications, symptoms, diagnoses = [], [], []
    medication_details = []
    processed_entities = []

    for item in results:
        entity_text = clean_entity_text(clinical_note, item)
        entity_group = item.get("entity_group", "").strip()
        if not entity_text:
            continue

        entity_text_norm = normalize_text(entity_text)
        group = entity_group.lower()

        processed_entities.append({
            "text": entity_text,
            "normalized_text": entity_text_norm,
            "entity_group": entity_group,
            "source": "bert",
            # The model returns numpy.float32, which FastAPI cannot serialise to JSON.
            "score": round(float(item["score"]), 4) if item.get("score") is not None else None,
            "start": item.get("start"),
            "end": item.get("end"),
        })

        if group == "medication":
            if entity_text_norm in GENERIC_MEDICATION_WORDS:
                continue
            medications.append(entity_text)
            if not any(normalize_text(d["name"]) == entity_text_norm for d in medication_details):
                medication_details.append({"name": entity_text, "dosage": None})
        elif group == "dosage" and medication_details and medication_details[-1]["dosage"] is None:
            # dose follows its drug in the note; keep its unit ("81" -> "81 mg")
            medication_details[-1]["dosage"] = clean_entity_text(
                clinical_note, complete_dosage(clinical_note, item))
        elif group in SYMPTOM_GROUPS:
            (diagnoses if entity_text_norm in KNOWN_DIAGNOSES else symptoms).append(entity_text)
        elif group in DIAGNOSIS_GROUPS:
            diagnoses.append(entity_text)

    # Safety net: common terms the model missed are added from a small dictionary
    # and marked with source="dictionary" so it is clear where they came from.
    for term in dictionary_matches(clinical_note, KNOWN_MEDICATIONS, medications):
        medications.append(term)
        medication_details.append({"name": term, "dosage": None})
        processed_entities.append({"text": term, "normalized_text": term,
                                   "entity_group": "Medication", "source": "dictionary"})
    for term in dictionary_matches(clinical_note, KNOWN_SYMPTOMS, symptoms + diagnoses):
        symptoms.append(term)
        processed_entities.append({"text": term, "normalized_text": term,
                                   "entity_group": "Sign_symptom", "source": "dictionary"})
    for term in dictionary_matches(clinical_note, KNOWN_DIAGNOSES, diagnoses + symptoms):
        # 'chronic kidney disease' replaces the shorter 'kidney disease' found by the model
        diagnoses[:] = [d for d in diagnoses if normalize_text(d) not in term]
        diagnoses.append(term)
        processed_entities.append({"text": term, "normalized_text": term,
                                   "entity_group": "Disease_disorder", "source": "dictionary"})

    return {
        "clinical_note": clinical_note,
        "medications": unique_keep_order(medications),
        "medication_details": medication_details,
        "symptoms": unique_keep_order(symptoms),
        "diagnoses": unique_keep_order(diagnoses),
        "raw_entities": processed_entities,
    }


def extract_entities_with_bert(clinical_note: str):
    return structure_entities(clinical_note, get_ner_pipeline()(clinical_note))
