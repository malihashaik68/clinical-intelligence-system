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
    from backend.app.main import app
    with TestClient(app) as c:
        yield c
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
    assert any(rec["id"] == record_id for rec in records)


def test_keyword_baseline_route(client):
    r = client.post("/extract/from-note-keywords",
                    json={"clinical_note": "Diabetes on metformin, reports fever."})
    assert r.status_code == 200
    e = r.json()["extracted_entities"]
    assert e["medications"] == ["metformin"] and e["diagnoses"] == ["diabetes"]


def test_health(client):
    assert client.get("/").json() == {"message": "Backend running"}


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
