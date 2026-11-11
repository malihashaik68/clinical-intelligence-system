"""Clinical Intelligence: public demo dashboard (Streamlit).

Runs the same backend pipeline in-process (no separate API server needed):
BERT NER -> severity flag -> RxNorm / OpenFDA / PubMed -> SQLite + ChromaDB -> RAG.

Run locally:   streamlit run streamlit_app/app.py
Deploy:        share.streamlit.io -> this repo -> main file streamlit_app/app.py

On Streamlit Community Cloud the 2.2 GB TinyLlama step is off by default
(RAG answers are then built from the retrieved record). Set RAG_USE_LLM=1 to enable it.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # database and vector store live in the project root
os.environ.setdefault("RAG_USE_LLM", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from backend.app.db.database import init_db  # noqa: E402
from backend.app.services.analytics_service import get_analytics_summary  # noqa: E402
from backend.app.services.clinical_pipeline_service import run_clinical_pipeline_from_note  # noqa: E402
from backend.app.services.rag_service import USE_LLM, generate_rag_response  # noqa: E402
from backend.app.services.record_service import save_clinical_record  # noqa: E402
from backend.app.services.retrieve_service import get_all_clinical_records  # noqa: E402
from backend.app.services.vector_service import get_collection, get_embedding_model, store_record_embedding  # noqa: E402
from backend.app.utils.bert_entity_extractor import extract_entities_with_bert, get_ner_pipeline  # noqa: E402
from backend.app.utils.severity import assess_severity  # noqa: E402

st.set_page_config(page_title="Clinical Intelligence", page_icon="🩺", layout="wide")

SAMPLES = {
    "Cardiac risk": "58-year-old female with a history of hypertension and type 2 diabetes presents with chest pain and shortness of breath for two days. She reports fatigue and dizziness. Current medications include metformin 500 mg twice daily and lisinopril 10 mg daily. Started aspirin 81 mg.",
    "Pneumonia": "Patient diagnosed with pneumonia. Complains of fever, cough and nausea. Prescribed amoxicillin 500 mg three times daily and ibuprofen as needed.",
    "Asthma & depression": "History of asthma and depression. Presents with headache and abdominal pain. Takes albuterol inhaler and sertraline 50 mg.",
    "Heart failure": "65-year-old male with heart failure and chronic kidney disease reports shortness of breath, fatigue and leg swelling. On furosemide 40 mg daily and atorvastatin 20 mg.",
    "Migraine": "Young woman with migraine reports severe headache, nausea and sensitivity to light. Took sumatriptan 50 mg with partial relief.",
}
SEV_STYLE = {"high": ("🔴", "High priority"), "medium": ("🟠", "Medium priority"), "low": ("🟢", "Low priority")}


@st.cache_resource(show_spinner="Loading the BERT model and vector index (first start takes about a minute)…")
def warm_up() -> bool:
    """Load models once and seed the store with example cases so search works immediately."""
    init_db()
    get_ner_pipeline()
    get_embedding_model()
    if get_collection().count() == 0 and get_all_clinical_records(limit=1)["total"] == 0:
        for note in SAMPLES.values():
            entities = extract_entities_with_bert(note)
            entities["severity"] = assess_severity(entities)
            # Seed quickly: skip the slow external lookups for the example cases.
            saved = save_clinical_record(note, entities, {"note": "example case, grounding skipped"})
            store_record_embedding(saved["record_id"], note, entities)
    return True


def badge(level: str | None) -> str:
    icon, label = SEV_STYLE.get(level or "low", ("⚪", level or "unknown"))
    return f"{icon} {label}"


def short(text: str | None, n: int = 260) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n] + "…"


warm_up()

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🩺 Clinical Intelligence")
    st.caption("Turns unstructured physician notes into structured, source-grounded clinical insight.")
    st.markdown(
        "**Pipeline**\n"
        "1. BERT NER (Hugging Face)\n"
        "2. Rule-based severity flag\n"
        "3. RxNorm · OpenFDA · PubMed grounding\n"
        "4. SQLite + ChromaDB vector store\n"
        "5. RAG over similar past cases"
    )
    st.info("Decision-support demo on synthetic notes. Not medical advice.")
    st.markdown("[Source code on GitHub](https://github.com/malihashaik68/clinical-intelligence-system)")

tab_note, tab_rag, tab_records, tab_eval = st.tabs(
    ["Analyse a note", "Similar cases (RAG)", "Records & analytics", "Model evaluation"])

# ------------------------------------------------------------ analyse note
with tab_note:
    choice = st.selectbox("Start from an example, or write your own note below", list(SAMPLES))
    note = st.text_area("Clinical note", value=SAMPLES[choice], height=130, key=f"note_{choice}")
    if st.button("Analyse note", type="primary", disabled=not note.strip()):
        with st.spinner("Extracting entities and querying RxNorm, OpenFDA and PubMed (about 20–30 s)…"):
            try:
                st.session_state.result = run_clinical_pipeline_from_note(note)
            except Exception as exc:  # show the problem instead of a blank page
                st.error(f"Analysis failed: {exc}")

    result = st.session_state.get("result")
    if result:
        e, sev = result["extracted_entities"], result["severity"]
        ctx = result["api_results"]["structured_context"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Priority", f"{SEV_STYLE[sev['level']][0]} {sev['level'].capitalize()}")
        c2.metric("Medications", len(e["medication_details"]))
        c3.metric("Symptoms", len(e["symptoms"]))
        c4.metric("Diagnoses", len(e["diagnoses"]))
        if sev["reasons"]:
            st.markdown("**Why this priority:** " + " · ".join(sev["reasons"]))

        c1, c2, c3 = st.columns(3)
        with c1:
            st.subheader("💊 Medications")
            for m in e["medication_details"]:
                st.markdown(f"- **{m['name']}**" + (f" — {m['dosage']}" if m["dosage"] else ""))
        with c2:
            st.subheader("🤒 Symptoms")
            for s in e["symptoms"] or ["none found"]:
                st.markdown(f"- {s}")
        with c3:
            st.subheader("🩺 Diagnoses")
            for d in e["diagnoses"] or ["none found"]:
                st.markdown(f"- {d}")

        with st.expander(f"Model output: {len(e['raw_entities'])} raw entities with confidence"):
            st.dataframe(pd.DataFrame(e["raw_entities"]).drop(columns=["normalized_text"], errors="ignore"),
                         hide_index=True, use_container_width=True)

        st.subheader("Drug information (RxNorm · OpenFDA)")
        cols = st.columns(max(1, min(3, len(ctx["medications"]))))
        for i, m in enumerate(ctx["medications"]):
            label = (m["openfda"].get("results") or [{}])[0]
            with cols[i % len(cols)]:
                st.markdown(f"**{m['input_name']}** · RxCUI `{m['rxnorm'].get('rxcui') or 'not found'}`")
                if label:
                    st.caption("Indications: " + short((label.get("indications_and_usage") or [""])[0]))
                    st.caption("Warnings: " + (short((label.get("warnings") or [""])[0]) or "–"))
                else:
                    st.caption("No FDA label found.")

        st.subheader("Supporting literature (PubMed)")
        for lit in ctx["literature"]:
            a = (lit.get("results") or [None])[0]
            if a:
                st.markdown(f"- *{lit['query']}*: [{a['title']}](https://pubmed.ncbi.nlm.nih.gov/{a['pmid']}/) "
                            f"<small>({a['source']}, {a['pubdate']})</small>", unsafe_allow_html=True)
            else:
                st.markdown(f"- *{lit['query']}*: no article found")
        st.success(f"Saved as record #{result['database']['record_id']}: it is now searchable in the other tabs.")

# --------------------------------------------------------------------- RAG
with tab_rag:
    st.markdown("Finds the most similar stored notes with **vector search** (sentence-transformer "
                "embeddings in ChromaDB) and summarises what they suggest.")
    query = st.text_input("Describe a patient", "Elderly patient with shortness of breath and fatigue")
    if st.button("Find similar cases", type="primary", disabled=not query.strip()):
        with st.spinner("Searching…"):
            st.session_state.rag = generate_rag_response(query)
    rag = st.session_state.get("rag")
    if rag:
        source = rag.get("summary_source", "template")
        st.markdown("#### Answer")
        st.code(rag["generated_answer"], language=None)
        st.caption("Summary written by the local LLM (TinyLlama)." if source == "llm" else
                   "LLM step is off in this online demo (it needs 2.2 GB); facts come from the most similar record.")
        st.markdown("#### Retrieved records")
        for m in rag["matches"]:
            with st.container(border=True):
                st.markdown(f"**Record #{m['record_id']}** · {badge(m.get('severity'))} · "
                            f"distance {m['distance']:.3f}")
                st.write(m["clinical_note"])
                st.caption(f"Diagnoses: {m['diagnoses'] or '–'} · Symptoms: {m['symptoms'] or '–'}")
    if not USE_LLM:
        st.caption("Running with RAG_USE_LLM=0.")

# --------------------------------------------------------- records & stats
with tab_records:
    stats = get_analytics_summary()
    sev = stats.get("severity_counts", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Notes analysed", stats["total_records"])
    c2.metric("🔴 High priority", sev.get("high", 0))
    c3.metric("🟠 Medium priority", sev.get("medium", 0))
    c4.metric("🟢 Low priority", sev.get("low", 0))

    c1, c2, c3 = st.columns(3)
    for col, key, title in [(c1, "top_diagnoses", "Top diagnoses"), (c2, "top_symptoms", "Top symptoms"),
                            (c3, "top_medications", "Top medications")]:
        with col:
            st.markdown(f"**{title}**")
            data = pd.DataFrame(stats[key], columns=["name", "count"]).set_index("name")
            if len(data):
                st.bar_chart(data, horizontal=True, height=220)

    flt = st.text_input("Filter records by diagnosis", placeholder="e.g. asthma")
    recs = get_all_clinical_records(diagnosis=flt or None, limit=100)
    rows = [{
        "#": r["id"],
        "priority": badge((r["extracted_entities"].get("severity") or {}).get("level")),
        "diagnoses": ", ".join(r["extracted_entities"]["diagnoses"]),
        "symptoms": ", ".join(r["extracted_entities"]["symptoms"]),
        "medications": ", ".join(r["extracted_entities"]["medications"]),
        "note": r["clinical_note"],
    } for r in recs["records"]]
    st.markdown(f"**Stored records ({recs['total']})**")
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

# -------------------------------------------------------------- evaluation
with tab_eval:
    results_path = ROOT / "evaluation" / "results.json"
    gold_path = ROOT / "evaluation" / "gold_notes.json"
    if results_path.exists():
        res = json.loads(results_path.read_text())
        n_notes = len(json.loads(gold_path.read_text()))
        b = res["BERT pipeline"]
        st.markdown(f"Entity extraction measured on **{n_notes} hand-labelled clinical notes** "
                    "(medications, symptoms, diagnoses), against a keyword baseline.")
        c1, c2, c3 = st.columns(3)
        c1.metric("F1 (strict, exact match)", f"{b['strict']['micro_avg']['f1']:.2f}")
        c2.metric("F1 (relaxed, partial match)", f"{b['relaxed']['micro_avg']['f1']:.2f}")
        c3.metric("Keyword baseline F1", f"{res['Keyword baseline']['strict']['micro_avg']['f1']:.2f}")
        table = []
        for system, scores in res.items():
            for cat in ["medications", "symptoms", "diagnoses", "micro_avg"]:
                s = scores["strict"][cat]
                table.append({"system": system, "category": "overall" if cat == "micro_avg" else cat,
                              "precision": s["precision"], "recall": s["recall"], "F1": s["f1"]})
        df = pd.DataFrame(table)
        st.bar_chart(df[df.category != "overall"], x="category", y="F1", color="system", stack=False, height=280)
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.caption("Strict = exact text match after normalisation. Small, synthetic test set: "
                   "treat the numbers as indicative. Reproduce with `python -m evaluation.evaluate`.")
    else:
        st.info("Run `python -m evaluation.evaluate` to produce the evaluation results.")
