from backend.app.utils.bert_entity_extractor import extract_entities_with_bert
from backend.app.utils.data_extractors import extract_clinical_context
from backend.app.utils.severity import assess_severity
from backend.app.services.record_service import save_clinical_record
from backend.app.services.vector_service import store_record_embedding


def run_clinical_pipeline_from_note(clinical_note: str):
    extracted_entities = extract_entities_with_bert(clinical_note)
    extracted_entities["severity"] = assess_severity(extracted_entities)
    api_results = extract_clinical_context(extracted_entities)

    db_result = save_clinical_record(
        clinical_note=clinical_note,
        extracted_entities=extracted_entities,
        api_results=api_results
    )

    store_record_embedding(
        record_id=db_result["record_id"],
        clinical_note=clinical_note,
        extracted_entities=extracted_entities
    )

    return {
        "extracted_entities": extracted_entities,
        "api_results": api_results,
        "severity": extracted_entities["severity"],
        "database": db_result
    }