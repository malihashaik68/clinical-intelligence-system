from transformers import pipeline

ner_pipeline = pipeline(
    "token-classification",
    model="d4data/biomedical-ner-all",
    aggregation_strategy="simple"
)

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


def extract_entities_with_bert(clinical_note: str):
    results = ner_pipeline(clinical_note)

    medications = []
    symptoms = []
    diagnoses = []
    processed_entities = []

    for item in results:
        entity_text = clean_entity_text(clinical_note, item)
        entity_group = item.get("entity_group", "").strip()

        if not entity_text:
            continue

        entity_text_norm = normalize_text(entity_text)
        entity_group_lower = entity_group.lower()

        processed_entities.append({
            "text": entity_text,
            "normalized_text": entity_text_norm,
            "entity_group": entity_group,
            "score": item.get("score"),
            "start": item.get("start"),
            "end": item.get("end"),
        })

        if entity_group_lower == "medication":
            medications.append(entity_text)

        elif entity_group_lower in {"sign_symptom", "symptom"}:
            if entity_text_norm in KNOWN_DIAGNOSES:
                diagnoses.append(entity_text)
            elif entity_text_norm in KNOWN_SYMPTOMS:
                symptoms.append(entity_text)
            else:
                symptoms.append(entity_text)

        elif entity_group_lower in {"disease_disorder", "disease", "diagnosis"}:
            diagnoses.append(entity_text)

    medications = unique_keep_order(medications)
    symptoms = unique_keep_order(symptoms)
    diagnoses = unique_keep_order(diagnoses)

    return {
        "clinical_note": clinical_note,
        "medications": medications,
        "symptoms": symptoms,
        "diagnoses": diagnoses,
        "raw_entities": processed_entities
    }