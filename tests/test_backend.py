"""Backend tests. The BERT model and the external APIs are replaced with
recorded outputs, so these run in seconds without internet access."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_clinical.db"

import pytest
from fastapi.testclient import TestClient

from backend.app.utils import bert_entity_extractor as bert
from backend.app.utils import data_extractors

NOTE = ("58-year-old female with a history of hypertension and type 2 diabetes presents with "
        "chest pain and shortness of breath for two days. She reports fatigue and dizziness. "
        "Current medications include metformin 500 mg twice daily and lisinopril 10 mg daily. "
        "Started aspirin 81 mg.")


_cursor = {"pos": 0}


def ent(word, group, score=0.99, note=None):
    """Recorded entity; its position is found in the note (searching forward)."""
    note = note or NOTE
    start = note.index(word, _cursor["pos"] if note is NOTE else 0)
    if note is NOTE:
        _cursor["pos"] = start + len(word)
    return {"word": word, "entity_group": group, "start": start, "end": start + len(word),
            "score": score}


# Real output of d4data/biomedical-ner-all for NOTE (recorded), including its quirks:
# 'dizziness' split in two, 'chest' tagged separately, the word 'medications' tagged as a drug.
RAW = [
    ent("hypertension", "History"), ent("type 2 diabetes", "History"),
    ent("chest", "Biological_structure"), ent("pain", "Sign_symptom"),
    ent("shortness of breath", "Sign_symptom"), ent("fatigue", "Sign_symptom"),
    ent("di", "Sign_symptom"), ent("zziness", "Sign_symptom"),
    ent("medications", "Medication"), ent("metformin", "Medication"),
    ent("500 mg twice daily", "Dosage"), ent("lisinopril", "Medication"),
    ent("10 mg", "Dosage"), ent("aspirin", "Medication"), ent("81", "Dosage"),
]


def test_recorded_offsets_match_note():
    for r in RAW:
        assert NOTE[r["start"]:r["end"]] == r["word"], r


def test_structure_entities_cleans_model_output():
    e = bert.structure_entities(NOTE, RAW)
    assert e["medications"] == ["metformin", "lisinopril", "aspirin"]  # 'medications' dropped
    assert e["medication_details"] == [
        {"name": "metformin", "dosage": "500 mg twice daily"},
        {"name": "lisinopril", "dosage": "10 mg"},
        {"name": "aspirin", "dosage": "81 mg"},                   # unit completed
    ]
    assert e["symptoms"] == ["chest pain", "shortness of breath", "fatigue", "dizziness"]
    assert e["diagnoses"] == ["hypertension", "type 2 diabetes"]  # 'History' counts
    assert all(isinstance(r["score"], float) for r in e["raw_entities"] if r["source"] == "bert")


def test_dictionary_safety_net_adds_missed_terms_and_marks_them():
    note = "Complains of fever, cough and nausea."
    e = bert.structure_entities(note, [ent("cough", "Sign_symptom", note=note)])
    assert e["symptoms"] == ["cough", "nausea", "fever"]
    sources = {r["text"]: r["source"] for r in e["raw_entities"]}
    assert sources == {"cough": "bert", "nausea": "dictionary", "fever": "dictionary"}


def test_dictionary_does_not_match_inside_other_words():
    e = bert.structure_entities("Feverish child, no coughing.", [])
    assert e["symptoms"] == []


@pytest.fixture
def client(monkeypatch):
    import numpy as np
    # numpy.float32 scores reproduce the original JSON serialisation crash.
    monkeypatch.setattr(bert, "get_ner_pipeline",
                        lambda: (lambda text: [{**r, "score": np.float32(r["score"])} for r in RAW]))
    monkeypatch.setattr(data_extractors, "normalize_drug_rxnorm",
                        lambda name: {"input_name": name, "matched": True, "rxcui": "1"})
    monkeypatch.setattr(data_extractors, "search_openfda_drug",
                        lambda name, limit=3: {"drug_name": name, "count": 1, "results": []})
    monkeypatch.setattr(data_extractors, "pubmed_lookup",
                        lambda q, retmax=5: {"query": q, "count": 0, "results": []})
    # Vector store: keep stored notes in memory instead of ChromaDB + embeddings.
    from backend.app.services import clinical_pipeline_service, rag_service
    from backend.app.routes import search_routes
    stored = []
    monkeypatch.setattr(clinical_pipeline_service, "store_record_embedding",
                        lambda record_id, clinical_note, extracted_entities: stored.append(
                            {"record_id": str(record_id), "clinical_note": clinical_note,
                             "diagnoses": ", ".join(extracted_entities["diagnoses"]),
                             "symptoms": ", ".join(extracted_entities["symptoms"]),
                             "medications": ", ".join(extracted_entities["medications"]),
                             "distance": 0.1}))
    fake_search = lambda query, top_k=3: {"query": query, "matches": stored[:top_k]}
    monkeypatch.setattr(search_routes, "search_similar_records", fake_search)
    monkeypatch.setattr(rag_service, "search_similar_records", fake_search)
    monkeypatch.setattr(rag_service, "USE_LLM", False)
    from backend.app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def _remove_test_db():
    yield
    if os.path.exists("test_clinical.db"):
        os.remove("test_clinical.db")


def test_from_note_runs_bert_pipeline_and_saves_record(client):
    r = client.post("/extract/from-note", json={"clinical_note": NOTE})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "raw_entities" in body["extracted_entities"]  # BERT route, not the keyword one
    meds = body["api_results"]["structured_context"]["medications"]
    assert [m["input_name"] for m in meds] == ["metformin", "lisinopril", "aspirin"]
    queries = [x["query"] for x in body["api_results"]["structured_context"]["literature"]]
    assert "hypertension treatment" in queries and "chest pain diagnosis" in queries
    record_id = body["database"]["record_id"]

    records = client.get("/records/").json()
    assert records["total"] >= 1
    assert any(rec["id"] == record_id for rec in records["records"])
    one = client.get(f"/records/{record_id}").json()
    assert one["clinical_note"] == NOTE and one["created_at"]
    filtered = client.get("/records/", params={"diagnosis": "hypertension"}).json()
    assert filtered["total"] >= 1


def test_search_rag_and_analytics_after_saving_a_note(client):
    client.post("/extract/from-note", json={"clinical_note": NOTE})

    matches = client.post("/search/", json={"query": "chest pain"}).json()["matches"]
    assert matches and "hypertension" in matches[0]["diagnoses"]

    rag = client.post("/rag/", json={"query": "patient with chest pain"}).json()
    assert rag["generated_answer"].startswith("Summary:")
    assert "Likely diagnosis: hypertension, type 2 diabetes" in rag["generated_answer"]

    stats = client.get("/analytics/summary").json()
    assert stats["total_records"] >= 1
    assert ["metformin", stats["top_medications"][0][1]] in [list(x) for x in stats["top_medications"]]


def test_context_route_validates_input(client):
    r = client.post("/extract/context", json={"medications": ["metformin"]})
    assert r.status_code == 200
    meds = r.json()["structured_context"]["medications"]
    assert meds[0]["input_name"] == "metformin"
    assert client.post("/extract/context", json={"medications": "not-a-list"}).status_code == 422


def test_health(client):
    assert client.get("/").json() == {"message": "Backend running"}
    assert client.get("/health/").json()["status"] == "ok"


def test_pubmed_retries_after_rate_limit(monkeypatch):
    calls = []

    class Resp:
        def __init__(self, status):
            self.status_code, self.headers = status, {"Retry-After": "0"}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

        def json(self):
            return {"esearchresult": {"idlist": ["123"]}}

    def fake_get(url, params, timeout):
        calls.append(params)
        return Resp(429 if len(calls) == 1 else 200)

    monkeypatch.setattr(data_extractors.requests, "get", fake_get)
    monkeypatch.setattr(data_extractors.time, "sleep", lambda s: None)
    assert data_extractors.search_pubmed("asthma treatment") == ["123"]
    assert len(calls) == 2
    assert calls[0]["sort"] == "relevance" and calls[0]["term"].endswith("[Title/Abstract]")



# --------------------------------------------------------- severity & RAG
from backend.app.utils.severity import assess_severity
from backend.app.services.rag_service import is_grounded


def test_severity_levels_and_reasons():
    high = assess_severity({"symptoms": ["chest pain", "fatigue"], "diagnoses": ["hypertension"]})
    assert high["level"] == "high"
    assert any("cardiac risk" in r for r in high["reasons"])
    medium = assess_severity({"symptoms": ["fever", "cough"], "diagnoses": ["pneumonia"]})
    assert medium["level"] == "medium" and len(medium["reasons"]) == 2
    assert assess_severity({"symptoms": ["headache"], "diagnoses": []})["level"] == "low"


def test_pipeline_returns_severity(client):
    body = client.post("/extract/from-note", json={"clinical_note": NOTE}).json()
    assert body["severity"]["level"] == "high"
    assert client.get("/analytics/summary").json()["severity_counts"]["high"] >= 1


def test_rag_grounding_rejects_facts_from_other_cases():
    top = {"diagnoses": "pneumonia", "symptoms": "fever, cough", "medications": "amoxicillin"}
    other = {"diagnoses": "asthma, depression", "symptoms": "headache", "medications": "sertraline"}
    assert is_grounded("Likely pneumonia; amoxicillin may help.", top, [top, other])
    assert not is_grounded("Aspirin for asthma and depression.", top, [top, other])


def test_longer_dictionary_term_replaces_shorter_model_term():
    n = "History of heart failure and chronic kidney disease, now with leg swelling."
    def e(w, g):
        s = n.index(w)
        return {"word": w, "entity_group": g, "start": s, "end": s + len(w), "score": 0.9}
    r = bert.structure_entities(n, [e("heart failure", "Disease_disorder"),
                                    e("kidney disease", "Disease_disorder")])
    assert r["diagnoses"] == ["heart failure", "chronic kidney disease"]
    assert r["symptoms"] == ["leg swelling"]
