"""Clinical Intelligence: private patient-history app for practitioners (Streamlit).

Practitioners log in and see the medical history of their hospital's patients, built
automatically from clinical notes by the note analyser (BERT NER + allergy extraction +
RxNorm / OpenFDA / PubMed). Records from other hospitals need patient consent (one-time
code) or emergency "break-the-glass" access, and every access is logged.

Run locally:  streamlit run streamlit_app/app.py
Deploy:       share.streamlit.io -> this repo -> main file streamlit_app/app.py
All patients, practitioners and notes are synthetic.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from backend.app.seed import DEMO_PASSWORD, PRACTITIONERS, HOSPITALS, seed_demo_data  # noqa: E402
from backend.app.services import patient_service as ps  # noqa: E402
from backend.app.services import qa_service  # noqa: E402
from backend.app.services.clinical_pipeline_service import analyse_note  # noqa: E402
from backend.app.services.emergency_card import render_card  # noqa: E402
from backend.app.services.fhir_service import build_fhir_bundle  # noqa: E402
from backend.app.services.summary_service import build_summary, fda_label_check  # noqa: E402
from backend.app.utils.bert_entity_extractor import get_ner_pipeline  # noqa: E402

st.set_page_config(page_title="Clinical Intelligence", page_icon="🩺", layout="wide")
SEV = {"high": "🔴 High", "medium": "🟠 Medium", "low": "🟢 Low", None: "–"}
ALERT_ICON = {"high": "🔴", "medium": "🟠", "low": "🟡"}


@st.cache_resource(show_spinner="Starting up: loading the BERT model and demo records (about a minute the first time)…")
def warm_up() -> bool:
    get_ner_pipeline()
    seed_demo_data()
    return True


warm_up()
state = st.session_state


# =================================================================== login
def login_page():
    st.title("🩺 Clinical Intelligence")
    st.markdown("#### Private medical history for practitioners, available in an emergency")
    st.markdown(
        "Patients rarely carry their medical history. When they arrive somewhere new, especially in an "
        "emergency, the doctor doesn't know their **allergies, medications or conditions**. This app builds each "
        "patient's history automatically from clinical notes and shares it **only with authorised "
        "practitioners**: other hospitals need patient consent or a logged emergency access.")
    left, right = st.columns([1, 1])
    with left:
        with st.form("login"):
            username = st.text_input("Username", placeholder="e.g. dr.lee")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", type="primary"):
                user = ps.authenticate(username, password)
                if user:
                    state.user, state.patient_id = user, None
                    st.rerun()
                st.error("Invalid username or password.")
    with right:
        st.markdown("**Demo accounts** (password `" + DEMO_PASSWORD + "`)")
        st.dataframe(pd.DataFrame([{"username": u, "name": n, "role": r, "hospital": HOSPITALS[h][0]}
                                   for u, n, r, h in PRACTITIONERS]), hide_index=True, width="stretch")
        st.caption("Try **dr.lee** (emergency physician at Riverside): search patient **HID-4821-7730** "
                   "(Priya Sharma, whose history is at City General) and use emergency access.")
    st.info("All patients, practitioners and notes are fictional. A demonstration of the concept, "
            "not a certified medical system.")


if "user" not in state:
    login_page()
    st.stop()

user: ps.User = state.user

# ================================================================= sidebar
with st.sidebar:
    st.markdown(f"### 🩺 Clinical Intelligence\n**{user.full_name}**  \n{user.role}  \n🏥 {user.hospital_name}")
    pages = ["My patients", "Find a patient", "Note analyser", "About & evaluation"]
    st.radio("Go to", pages, key="nav", on_change=lambda: state.update(patient_id=None))
    use_llm = st.toggle("Local LLM answers", value=qa_service.USE_LLM,
                        help="Lets a small local model (runs on this server) phrase answers from the notes.")
    if st.button("Log out"):
        state.clear()
        st.rerun()
    st.caption("Synthetic demo data · [Source code](https://github.com/malihashaik68/clinical-intelligence-system)")


def open_patient(pid: int):
    state.patient_id = pid
    st.rerun()


# =========================================================== access panel
def access_panel(pid: int, partial: bool):
    """Consent (one-time code) or emergency access for records held at other hospitals."""
    with st.container(border=True):
        st.markdown("#### 🔒 " + ("Records at other hospitals are locked" if partial else "No access to this patient"))
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Patient consent**: the patient approves with a code sent to their phone (7 days).")
            if st.button("Send code to patient", key=f"otp_{pid}"):
                state[f"sms_{pid}"] = ps.request_consent(user, pid)
            if state.get(f"sms_{pid}"):
                st.info(f"📱 Simulated SMS to patient: your code is **{state[f'sms_{pid}']}**")
                code = st.text_input("Code given by the patient", key=f"code_{pid}")
                if st.button("Confirm consent", key=f"confirm_{pid}"):
                    if ps.confirm_consent(user, pid, code):
                        state.pop(f"sms_{pid}")
                        st.success("Consent granted.")
                        st.rerun()
                    st.error("Wrong or expired code.")
        with c2:
            st.markdown("**🚨 Emergency access**: for when the patient can't consent. Lasts 24 h, logged, "
                        "and the patient and home hospital are notified.")
            reason = st.text_input("Reason", key=f"reason_{pid}", placeholder="e.g. unconscious after collapse")
            if st.button("Break the glass", key=f"glass_{pid}", type="primary"):
                try:
                    ps.emergency_access(user, pid, reason)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


# ========================================================== patient views
def show_alerts(alerts: list[dict]):
    for a in alerts:
        box = st.error if a["severity"] == "high" else st.warning
        box(f"{ALERT_ICON[a['severity']]} **{a['type'].capitalize()}**: {a['message']}  \n"
            f"Sources: {' · '.join(a['sources'])}")


def summary_tab(patient, summary):
    if summary["alerts"]:
        st.markdown("#### ⚠️ Safety alerts")
        show_alerts(summary["alerts"])
    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown("#### Allergies")
        if summary["allergies"]:
            for a in summary["allergies"]:
                st.error(f"**{a['substance']}**" + (f" ({a['reaction']})" if a.get("reaction") else "")
                         + f"  \nRecorded at {a['hospital']}, {a['date']}")
        elif summary["no_known_allergies"]:
            st.success("No known drug allergies")
        else:
            st.warning("No allergy information recorded")
        st.markdown("#### Conditions")
        for c in summary["conditions"] or [{"name": "None recorded", "first_seen": ""}]:
            st.markdown(f"- **{c['name']}**" + (f" <small>since {c['first_seen']}</small>" if c["first_seen"] else ""),
                        unsafe_allow_html=True)
        st.markdown(f"**Latest visit priority:** {SEV.get(summary['latest_severity'])}")
    with c2:
        st.markdown("#### Current medications")
        if summary["current_medications"]:
            st.dataframe(pd.DataFrame([{"medication": m["name"], "dose": m.get("dosage") or "–",
                                        "last noted": m["last_seen"], "hospital": m["hospital"]}
                                       for m in summary["current_medications"]]),
                         hide_index=True, width="stretch")
        else:
            st.caption("None recorded")
        if summary["older_medications"]:
            st.caption("Older (not mentioned in the last year): "
                       + ", ".join(m["name"] for m in summary["older_medications"]))
        if summary["current_medications"] and st.button("Check FDA labels against allergies"):
            allergens = tuple(a["substance"] for a in summary["allergies"])
            with st.spinner("Reading official FDA drug labels…"):
                for m in summary["current_medications"]:
                    res = fda_label_check(m["name"], allergens)
                    if res.get("matches"):
                        for hit in res["matches"]:
                            st.error(f"**{m['name']}** label mentions {hit['allergen']}: “{hit['text']}”")
                    elif res.get("found"):
                        st.caption(f"✅ {m['name']}: no mention of the patient's allergies on the FDA label.")
                    else:
                        st.caption(f"{m['name']}: no FDA label found.")


def ask_tab(pid, patient, summary, records):
    st.markdown("Answers come **only from this patient's accessible records**, with the source shown. "
                "Common questions are answered directly from the data; others use the local LLM with a "
                "check that rejects anything not in the notes.")
    examples = ["Any allergies?", "Is the patient on blood thinners?", "What medications are current?",
                "Can I give amoxicillin?", "What happened at the last visit?", "Does the patient smoke?"]
    cols = st.columns(3)
    for i, ex in enumerate(examples):
        if cols[i % 3].button(ex, key=f"ex_{pid}_{i}"):
            state[f"q_{pid}"] = ex
    with st.form(f"ask_{pid}", clear_on_submit=False):
        q = st.text_input("Your question", value=state.get(f"q_{pid}", ""))
        submitted = st.form_submit_button("Ask", type="primary")
    if submitted and q.strip():
        ps.log_event(user, pid, "ask", q[:200])
        with st.spinner("Searching the record…"):
            ans = qa_service.answer_question(q, summary, records, patient, use_llm=use_llm)
        state.setdefault(f"chat_{pid}", []).insert(0, (q, ans))
    for q, ans in state.get(f"chat_{pid}", []):
        with st.container(border=True):
            st.markdown(f"**Q: {q}**")
            st.markdown(ans["answer"].replace("\n", "  \n"))
            st.caption(f"Answered by: {ans['method']}")
            if ans.get("llm_note"):
                st.caption("ℹ️ " + ans["llm_note"])
            if ans["evidence"]:
                with st.expander("Source sentences"):
                    for e in ans["evidence"]:
                        st.markdown(f"- “{e['text']}” <small>(record #{e['record_id']}, {e['source']})</small>",
                                    unsafe_allow_html=True)


def add_note_tab(pid, before_alerts):
    st.markdown(f"New note for this visit at **{user.hospital_name}**. The note analyser extracts medications, "
                "doses, symptoms, diagnoses and allergies, then checks the combined history for new safety alerts.")
    with st.form(f"note_{pid}"):
        note = st.text_area("Clinical note", height=140,
                            placeholder="e.g. Presents with fever and cough. Prescribed amoxicillin 500 mg three times daily.")
        c1, c2 = st.columns(2)
        visit = c1.date_input("Visit date", value=date.today(), max_value=date.today())
        literature = c2.checkbox("Search PubMed for literature (slower)", value=False)
        go = st.form_submit_button("Analyse and save", type="primary")
    if go:
        if not note.strip():
            st.warning("Please write a note first.")
            return
        with st.spinner("Analysing the note…"):
            try:
                res = ps.add_visit_note(user, pid, note, visit, literature=literature)
            except Exception as exc:
                st.error(f"Could not analyse the note: {exc}")
                return
        e = res["extracted_entities"]
        st.success(f"Saved as record #{res['database']['record_id']} · priority {SEV.get(res['severity']['level'])}")
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown("**Medications**\n" + "\n".join(f"- {m['name']} {m.get('dosage') or ''}" for m in e["medication_details"]) or "–")
        c2.markdown("**Symptoms**\n" + "\n".join(f"- {s}" for s in e["symptoms"]) or "–")
        c3.markdown("**Diagnoses**\n" + "\n".join(f"- {d}" for d in e["diagnoses"]) or "–")
        c4.markdown("**Allergies**\n" + "\n".join(f"- {a['substance']}" for a in e["allergies"]) or "–")
        records = ps.visible_records(user, pid, log_action=None)
        new = [a for a in build_summary(records)["alerts"] if a["message"] not in {b["message"] for b in before_alerts}]
        if new:
            st.markdown("#### ⚠️ New safety alerts caused by this note")
            show_alerts(new)
        state[f"refresh_{pid}"] = True


def history_tab(summary):
    for v in summary["timeline"]:
        with st.expander(f"{v['date']} · {v['hospital']} · {SEV.get(v['severity'])} priority · {v['author']}"):
            st.write(v["note"])
            st.caption(f"Diagnoses: {', '.join(v['diagnoses']) or '–'} · Symptoms: {', '.join(v['symptoms']) or '–'}"
                       f" · Medications: {', '.join(v['medications']) or '–'}")


def card_tab(pid, patient, summary, records):
    st.markdown("A printable card with the life-critical facts. The patient keeps it (or a photo); any "
                "clinician can read it or scan the QR code, even with **no connection between hospitals**.")
    png = render_card(patient, summary)
    st.image(png, width="stretch")
    c1, c2 = st.columns(2)
    if c1.download_button("Download card (PNG)", png, f"emergency_card_{patient['health_id']}.png", "image/png"):
        ps.log_event(user, pid, "emergency_card")
    bundle = build_fhir_bundle(patient, summary, records)
    if c2.download_button("Export history as HL7 FHIR (JSON)", json.dumps(bundle, indent=2),
                          f"fhir_{patient['health_id']}.json", "application/json"):
        ps.log_event(user, pid, "export_fhir")
    counts = pd.Series([e["resource"]["resourceType"] for e in bundle["entry"]]).value_counts()
    st.caption("FHIR bundle: " + ", ".join(f"{n} {t}" for t, n in counts.items())
               + ". FHIR is the standard hospitals use to exchange records.")


def patient_page(pid: int):
    if st.button("← Back"):
        state.patient_id = None
        st.rerun()
    status = ps.access_status(user, pid)
    if not (status["own_hospital_records"] or status["other_hospital_records"]):
        hit = next((p for p in ps.search_patients(user, health_id=state.get("last_hid", "")) if p["id"] == pid), None)
        st.subheader(hit["full_name"] if hit else "Patient")
        if hit:
            st.caption(f"{hit['health_id']} · born {hit['date_of_birth']} · records at: "
                       + ", ".join(f"{h} ({n})" for h, n in hit["records_at"].items()))
        access_panel(pid, partial=False)
        return

    patient = ps.get_patient(user, pid)
    records = ps.visible_records(user, pid, log_action="view_records" if state.get("viewed") != pid else None)
    state.viewed = pid
    summary = build_summary(records)

    st.title(patient["full_name"])
    st.markdown(f"**{patient['age']} y · {patient['sex']} · Blood type {patient['blood_type'] or '?'} · "
                f"{patient['health_id']}**  \n📞 Emergency contact: {patient['emergency_contact'] or '–'}")
    where = ", ".join(f"{h} ({n})" for h, n in patient["records_at"].items())
    if status["grant_kind"] == "emergency":
        st.error(f"🚨 Emergency access active until {status['grant_expires']} UTC: logged and reported.")
    elif status["grant_kind"] == "consent":
        st.success(f"✅ Patient consent: records from all hospitals visible until {status['grant_expires']} UTC.")
    st.caption(f"Records exist at: {where or '–'}")
    hidden = ps.hidden_record_count(user, pid)
    if hidden:
        st.warning(f"{hidden} record(s) at other hospitals are not visible. Allergies or medications may be missing.")
        access_panel(pid, partial=True)

    tabs = st.tabs(["Emergency summary", "Ask about this patient", "Add visit note", "Visit history",
                    "Emergency card & FHIR", "Access log"])
    with tabs[0]:
        summary_tab(patient, summary)
    with tabs[1]:
        ask_tab(pid, patient, summary, records)
    with tabs[2]:
        add_note_tab(pid, summary["alerts"])
    with tabs[3]:
        history_tab(summary)
    with tabs[4]:
        card_tab(pid, patient, summary, records)
    with tabs[5]:
        log = ps.access_log(user, pid)
        st.caption("Every view, question, consent and emergency access is recorded.")
        st.dataframe(pd.DataFrame(log), hide_index=True, width="stretch")


# =============================================================== pages
def my_patients_page():
    st.title(f"Patients at {user.hospital_name}")
    patients = ps.my_patients(user)
    if not patients:
        st.info("No patients yet. Use **Find a patient** to look up someone from another hospital.")
    for p in patients:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{p['full_name']}** · {p['age']} y · {p['sex']} · {p['health_id']}  \n"
                        f"<small>Records at: {', '.join(f'{h} ({n})' for h, n in p['records_at'].items()) or '–'}</small>",
                        unsafe_allow_html=True)
            if c2.button("Open", key=f"open_{p['id']}"):
                open_patient(p["id"])


def find_patient_page():
    st.title("Find a patient")
    st.markdown("Search the network patient index. Results show **who the patient is and where records exist**, "
                "not the records themselves.")
    with st.form("search"):
        c1, c2, c3 = st.columns(3)
        hid = c1.text_input("Health ID", placeholder="HID-4821-7730")
        name = c2.text_input("…or name")
        dob = c3.date_input("Date of birth (with name)", value=None, min_value=date(1900, 1, 1), max_value=date.today())
        go = st.form_submit_button("Search", type="primary")
    if go:
        state.results = ps.search_patients(user, health_id=hid, name=name, dob=dob)
        state.last_hid = hid or (state.results[0]["health_id"] if state.results else "")
    for p in state.get("results", []):
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{p['full_name']}** · born {p['date_of_birth']} · {p['health_id']}  \n"
                        f"Records at: {', '.join(f'{h} ({n})' for h, n in p['records_at'].items()) or '–'}  \n"
                        f"<small>Match: {p['match']}</small>", unsafe_allow_html=True)
            if c2.button("Open", key=f"res_{p['id']}"):
                state.last_hid = p["health_id"]
                open_patient(p["id"])
    if go and not state.get("results"):
        st.info("No matching patient.")


def note_analyser_page():
    st.title("Note analyser")
    st.markdown("Analyse any clinical note without saving it: BERT entity extraction, allergies, severity, "
                "and grounding in **RxNorm**, **OpenFDA** and **PubMed**. The same engine builds patient histories.")
    with st.form("analyser"):
        note = st.text_area("Clinical note", height=140,
                            value="45-year-old man with epilepsy on levetiracetam 500 mg twice daily presents after "
                                  "a seizure with confusion and headache. Allergic to sulfa drugs.")
        literature = st.checkbox("Include PubMed literature (slower)", value=True)
        go = st.form_submit_button("Analyse", type="primary")
    if go and note.strip():
        with st.spinner("Analysing (about 10–30 s with lookups)…"):
            state.analysis = analyse_note(note, grounding=True, literature=literature)
    res = state.get("analysis")
    if not res:
        return
    e, sev = res["extracted_entities"], res["severity"]
    st.markdown(f"**Priority:** {SEV.get(sev['level'])}" + (f": {' · '.join(sev['reasons'])}" if sev["reasons"] else ""))
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown("**💊 Medications**\n" + ("\n".join(f"- {m['name']} {m.get('dosage') or ''}" for m in e["medication_details"]) or "–"))
    c2.markdown("**🤒 Symptoms**\n" + ("\n".join(f"- {s}" for s in e["symptoms"]) or "–"))
    c3.markdown("**🩺 Diagnoses**\n" + ("\n".join(f"- {d}" for d in e["diagnoses"]) or "–"))
    c4.markdown("**⚠️ Allergies**\n" + ("\n".join(f"- {a['substance']}" for a in e["allergies"]) or "–"))
    ctx = res["api_results"].get("structured_context", {})
    for m in ctx.get("medications", []):
        label = (m["openfda"].get("results") or [{}])[0]
        st.markdown(f"**{m['input_name']}** · RxCUI `{m['rxnorm'].get('rxcui') or '–'}` · "
                    + (" ".join((label.get("indications_and_usage") or [""])[0].split())[:240] + "…" if label else "no FDA label"))
    for lit in ctx.get("literature", []):
        a = (lit.get("results") or [None])[0]
        if a:
            st.markdown(f"- *{lit['query']}*: [{a['title']}](https://pubmed.ncbi.nlm.nih.gov/{a['pmid']}/)")
    with st.expander("Raw model output"):
        st.dataframe(pd.DataFrame(e["raw_entities"]), hide_index=True, width="stretch")


def about_page():
    st.title("About this project")
    st.markdown("""
**Problem.** Patients rarely carry their medical history. At a new hospital, especially in an emergency, the
doctor may not know their allergies, current medications or conditions.

**How it works**
1. **Note analyser**: a BERT NER model (Hugging Face) plus rules extracts medications with doses, symptoms,
   diagnoses and allergies from free-text notes, grounded in RxNorm, OpenFDA and PubMed.
2. **Patient history**: each hospital keeps its own notes; the app combines a patient's notes into one summary.
3. **Privacy**: practitioners log in and see their own hospital's records. Other hospitals' records need
   **patient consent** (one-time code) or **emergency access** with a reason, and every access is logged.
4. **Safety alerts**: allergy conflicts, drug interactions, duplicate drugs and dose differences between hospitals.
5. **Questions**: direct answers for common emergency questions; a **local LLM** (runs on the server, so no data is
   sent to outside companies) for others, with a check that rejects anything not in the notes.
6. **Emergency card & FHIR**: a QR card that works with no connection, and export in the HL7 FHIR standard.

*Demo on fictional data. A real deployment would need regulatory compliance (e.g. HIPAA, India's DPDP Act),
certified security and integration with hospital systems.*
""")
    results = ROOT / "evaluation" / "results.json"
    if results.exists():
        res = json.loads(results.read_text())
        b = res["BERT pipeline"]
        st.markdown("#### Note analyser evaluation (30 hand-labelled notes)")
        c1, c2, c3 = st.columns(3)
        c1.metric("F1 strict", f"{b['strict']['micro_avg']['f1']:.2f}")
        c2.metric("F1 relaxed", f"{b['relaxed']['micro_avg']['f1']:.2f}")
        c3.metric("Keyword baseline F1", f"{res['Keyword baseline']['strict']['micro_avg']['f1']:.2f}")
        rows = [{"system": s, "category": c, **{k: v[c][k] for k in ("precision", "recall", "f1")}}
                for s, v in ((s, sc["strict"]) for s, sc in res.items())
                for c in ["medications", "symptoms", "diagnoses", "micro_avg"]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


# =============================================================== router
nav = state.get("nav", "My patients")
if state.get("patient_id"):
    patient_page(state.patient_id)
elif nav == "Find a patient":
    find_patient_page()
elif nav == "Note analyser":
    note_analyser_page()
elif nav == "About & evaluation":
    about_page()
else:
    my_patients_page()
