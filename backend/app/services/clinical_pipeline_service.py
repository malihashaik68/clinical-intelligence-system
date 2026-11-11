from backend.app.services.record_service import save_clinical_record
from backend.app.services.vector_service import store_record_embedding
from backend.app.utils.allergy_extractor import extract_allergies
from backend.app.utils.bert_entity_extractor import extract_entities_with_bert
from backend.app.utils.data_extractors import extract_clinical_context
from backend.app.utils.severity import assess_severity


def _drop_allergy_words(entities: dict) -> None:
    """The NER model sometimes tags 'Allergic to penicillin' as a condition or drug;
    allergens belong in the allergy list only."""
    allergens = {a["substance"].lower() for a in entities.get("allergies", [])}
    noise = allergens | {"allergic", "allergy", "allergies"}

    def keep(term: str) -> bool:
        t = term.lower().strip()
        return t not in noise and not t.startswith("allerg")

    for key in ("diagnoses", "symptoms", "medications"):
        entities[key] = [t for t in entities.get(key, []) if keep(t)]
    entities["medication_details"] = [m for m in entities.get("medication_details", []) if keep(m["name"])]


def analyse_note(clinical_note: str, grounding: bool = True, literature: bool = True) -> dict:
    """Note analyser: entities, allergies and severity, plus optional RxNorm/OpenFDA/PubMed grounding."""
    entities = extract_entities_with_bert(clinical_note)
    entities.update(extract_allergies(clinical_note))
    _drop_allergy_words(entities)
    entities["severity"] = assess_severity(entities)
    api_results = (extract_clinical_context(entities, include_literature=literature)
                   if grounding else {"note": "grounding skipped"})
    return {"extracted_entities": entities, "api_results": api_results, "severity": entities["severity"]}


def run_clinical_pipeline_from_note(clinical_note: str, patient_id=None, hospital_id=None,
                                    practitioner_id=None, visit_date=None,
                                    grounding: bool = True, literature: bool = True):
    result = analyse_note(clinical_note, grounding=grounding, literature=literature)
    entities = result["extracted_entities"]

    db_result = save_clinical_record(
        clinical_note=clinical_note,
        extracted_entities=entities,
        api_results=result["api_results"],
        patient_id=patient_id,
        hospital_id=hospital_id,
        practitioner_id=practitioner_id,
        visit_date=visit_date,
    )

    # Only anonymous stand-alone notes go into the shared similarity index; patient notes
    # stay behind the access-control layer (see patient_service).
    if patient_id is None:
        store_record_embedding(
            record_id=db_result["record_id"],
            clinical_note=clinical_note,
            extracted_entities=entities,
        )

    return {**result, "database": db_result}
