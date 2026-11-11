# Clinical Intelligence System

Privacy-aware clinical intelligence backend that turns an unstructured physician note into structured clinical context: a transformer-based NER model extracts medications, doses, symptoms and diagnoses, then each entity is grounded in trusted medical sources (**RxNorm**, **OpenFDA**, **PubMed**) and the result is stored for later retrieval.

> Built as a team project for the Saint Peter's University Academic Symposium.
> **My contributions:** the backend: BERT entity-extraction pipeline, FastAPI API, and PubMed / OpenFDA / RxNorm integration.

## How it works

```
clinical note
   │
   ▼
BERT NER (d4data/biomedical-ner-all, Hugging Face)
   │  + post-processing: rejoin split words, "chest"+"pain" → "chest pain",
   │    attach doses to drugs, drop generic words, dictionary safety net
   ▼
medications (+dose) · symptoms · diagnoses
   │
   ├─► RxNorm   normalise each drug to its RxCUI
   ├─► OpenFDA  drug label: indications, warnings
   └─► PubMed   most relevant article per diagnosis / symptom / drug side effects
   ▼
structured clinical context ──► SQLite (SQLAlchemy) ──► GET /records
```

## Example (real output)

Input note:
> 58-year-old female with a history of hypertension and type 2 diabetes presents with chest pain and shortness of breath for two days. She reports fatigue and dizziness. Current medications include metformin 500 mg twice daily and lisinopril 10 mg daily. Started aspirin 81 mg.

Extracted:

| Type | Entities |
|---|---|
| Medications | metformin, 500 mg twice daily · lisinopril, 10 mg · aspirin, 81 mg |
| Symptoms | chest pain · shortness of breath · fatigue · dizziness |
| Diagnoses | hypertension · type 2 diabetes |

Grounding: RxNorm RxCUIs metformin `6809`, lisinopril `29046`, aspirin `1191`; 3 OpenFDA labels per drug; PubMed, e.g. *hypertension treatment* → "2024 ESC Guidelines for the management of elevated blood pressure and hypertension" (PMID 39210715), *metformin adverse effects* → "Adverse Effects of Metformin From Diabetes to COVID-19, Cancer, Neurodegenerative Diseases…" (PMID 34671273).

## API

| Method | Path | What it does |
|---|---|---|
| POST | `/extract/from-note` | Full pipeline: BERT NER → RxNorm / OpenFDA / PubMed → saved record |
| POST | `/extract/from-note-keywords` | Fast keyword baseline (no model) |
| POST | `/extract/context` | Grounding only, for entities you already have |
| GET | `/rxnorm/normalize?drug_name=` | RxNorm lookup |
| GET | `/openfda/drug?drug_name=` | OpenFDA drug labels |
| GET | `/pubmed/search?query=` | PubMed search |
| GET | `/records/` | All saved records |

Interactive docs: http://localhost:8000/docs

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # small CPU-only build
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

```bash
curl -X POST http://localhost:8000/extract/from-note \
  -H "content-type: application/json" \
  -d '{"clinical_note": "History of asthma. Presents with headache. Takes sertraline 50 mg."}'
```

The first request downloads the NER model (~260 MB). A full request takes ~30 s, mostly PubMed (NCBI allows ~3 requests/second without an API key; the client backs off and retries on rate limits).

## Tests

```bash
pytest -q
```

The tests use recorded model output and stubbed APIs, so they run in under a second without internet access. They cover the entity clean-up (split words, body part + symptom, doses, dictionary safety net), the full `/extract/from-note` route with database save and retrieval, the keyword route, and PubMed retry on rate limits.

## Limitations

- No negation handling yet: "denies fever" would still list fever.
- The dictionary safety net covers a short list of common terms only.
- The NER model is general biomedical, not fine-tuned on clinical notes.
- PubMed returns the top article by relevance; it is a pointer to literature, not a clinical recommendation.
- The React frontend in `frontend/` is still the Vite starter template.

## Tech stack

Python · FastAPI · Hugging Face Transformers (BERT NER) · PyTorch · SQLAlchemy / SQLite · RxNorm, OpenFDA and PubMed (NCBI E-utilities) APIs · pytest · React (Vite)
