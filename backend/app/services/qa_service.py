"""Ask questions about one patient, answered only from records the practitioner may see.

Layers, from most to least reliable:
  1. Direct answers from the structured summary for common emergency questions
     (allergies, current medications, blood thinners, conditions, last visit,
     "can I give <drug>?"). No LLM involved.
  2. Evidence retrieval: the patient's note sentences are embedded (all-MiniLM-L6-v2)
     and the most relevant ones selected. If nothing is relevant -> "not documented"
     (the LLM is never asked, so it cannot invent an answer).
  3. "Why" questions whose evidence states no reason -> "the record does not state the reason".
  4. Local LLM (Qwen2.5-Instruct, runs on the server: patient data is not sent to any
     outside company) rewrites the evidence into a short answer; a grounding check rejects
     answers naming drugs, conditions or numbers that are not in the evidence.
Every answer returns its source sentences so the clinician can verify it.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

from backend.app.services.summary_service import safety_alerts
from backend.app.utils.drug_knowledge import BLOOD_THINNER_CLASSES, DRUG_CLASSES, base_name, classes_of

QA_MODEL = os.getenv("QA_LLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
USE_LLM = os.getenv("QA_USE_LLM", "1") != "0"
RELEVANCE_THRESHOLD = float(os.getenv("QA_RELEVANCE_THRESHOLD", "0.35"))
ALL_DRUGS = sorted({d for members in DRUG_CLASSES.values() for d in members}, key=len, reverse=True)
CAUSAL_WORDS = re.compile(r"\b(because|due to|for|to treat|to prevent|indicated|secondary to|after|given)\b", re.I)

SYSTEM_PROMPT = (
    "You are a clinical assistant helping a doctor. Answer the question using ONLY the evidence sentences. "
    "Do not add medical knowledge, reasons or advice that are not written in the evidence. "
    "If the evidence does not answer the question, reply exactly: The record does not state this. "
    "Cite the record id in brackets, for example [R3]. One or two short sentences."
)


def _src(item: dict) -> str:
    return f"{item.get('hospital', '')}, {item.get('date') or item.get('last_seen', '')}"


def _answer(text: str, method: str, evidence: list[dict] | None = None) -> dict:
    return {"answer": text, "method": method, "evidence": evidence or []}


# --------------------------------------------------------- 1. direct answers
OPEN_QUESTION = re.compile(r"^\s*(why|how|when|what happened|describe|explain|tell me about)\b", re.I)


def _direct_answer(question: str, summary: dict, patient: dict) -> dict | None:
    q = question.lower()
    meds, older = summary["current_medications"], summary["older_medications"]
    if OPEN_QUESTION.match(q):
        return None  # narrative questions are answered from the notes, not the summary lists

    names = sorted(set(ALL_DRUGS) | {base_name(m["name"]) for m in meds + older}, key=len, reverse=True)
    mentioned = next((d for d in names if re.search(rf"\b{re.escape(d)}\b", q)), None)
    if mentioned and re.search(r"\b(give|prescribe|start|administer|safe|can i|could i|ok to)\b", q):
        trial = {**summary, "current_medications": meds + [{
            "name": mentioned, "dosage": None, "last_seen": "proposed", "hospital": "proposed",
            "history": []}]}
        new = [a for a in safety_alerts(trial) if mentioned in a["message"]]
        if new:
            lines = [f"⚠️ {a['message']} ({a['severity']})" for a in new]
            return _answer(f"Caution before giving {mentioned}:\n" + "\n".join(lines), "safety check")
        return _answer(f"No conflict found for {mentioned} with the documented allergies and current "
                       f"medications. This check covers common rules only; clinical judgement still applies.",
                       "safety check")

    if mentioned:
        hit = next((m for m in meds + older if base_name(m["name"]) == mentioned), None)
        if hit:
            state = "an older medication (not mentioned in the last year)" if hit.get("stale") else "currently recorded"
            return _answer(f"Yes: {hit['name']} {hit.get('dosage') or ''} is {state}, last noted "
                           f"{hit['last_seen']} at {hit['hospital']}.".replace("  ", " "), "summary")
        return _answer(f"No record of {mentioned} in the records you can access.", "summary")

    if "allerg" in q:
        if summary["allergies"]:
            items = [f"{a['substance']}" + (f" ({a['reaction']})" if a.get("reaction") else "")
                     + f" [{_src(a)}]" for a in summary["allergies"]]
            return _answer("Documented allergies: " + "; ".join(items), "summary")
        if summary["no_known_allergies"]:
            return _answer("No known drug allergies are documented.", "summary")
        return _answer("No allergy information is documented in the accessible records. Ask the patient "
                       "or family if possible.", "summary")

    if re.search(r"blood thinner|anticoagul|antiplatelet|bleed", q):
        thinners = [m for m in meds if classes_of(m["name"]) & set(BLOOD_THINNER_CLASSES)]
        if thinners:
            return _answer("Yes. Blood thinners: " + "; ".join(
                f"{m['name']} {m.get('dosage') or ''} [{_src(m)}]".replace("  ", " ") for m in thinners), "summary")
        return _answer("No anticoagulant or antiplatelet drug is recorded as current.", "summary")

    if re.search(r"\b(medication|medicine|meds|drugs?|taking|prescri)", q):
        if not meds:
            return _answer("No current medications are recorded.", "summary")
        text = "Current medications: " + "; ".join(
            f"{m['name']} {m.get('dosage') or ''} [{_src(m)}]".replace("  ", " ") for m in meds)
        if older:
            text += ". Older (not mentioned in the last year): " + ", ".join(m["name"] for m in older)
        return _answer(text, "summary")

    if re.search(r"\b(condition|diagnos|problems?|diseases?|medical history|past history)", q):
        if not summary["conditions"]:
            return _answer("No conditions are recorded.", "summary")
        return _answer("Conditions: " + "; ".join(
            f"{c['name']} (first noted {c['first_seen']})" for c in summary["conditions"]), "summary")

    if re.search(r"\b(last|latest|recent|most recent) (visit|admission|encounter)", q):
        if not summary["timeline"]:
            return _answer("No visits are recorded.", "summary")
        v = summary["timeline"][0]
        return _answer(f"Last visit: {v['date']} at {v['hospital']} ({v['severity']} priority). {v['note']}",
                       "summary", [{"record_id": v["record_id"], "text": v["note"], "source": _src(v)}])

    if re.search(r"\b(alerts?|interactions?|risks?|warnings?)\b", q):
        if not summary["alerts"]:
            return _answer("No medication safety alerts for the accessible records.", "summary")
        return _answer("\n".join(f"⚠️ {a['message']} ({a['severity']})" for a in summary["alerts"]), "summary")

    if re.search(r"blood (type|group)", q):
        return _answer(f"Blood type: {patient.get('blood_type') or 'not recorded'}.", "summary")
    return None


# ------------------------------------------------------- 2. evidence search
def _sentences(records: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for r in records:
        for s in re.split(r"(?<=[.!?])\s+", r["clinical_note"].strip()):
            if len(s) > 3 and s.strip().lower() not in seen:
                seen.add(s.strip().lower())
                out.append({"record_id": r["id"], "text": s.strip(), "source": f"{r['hospital']}, {r['visit_date']}"})
    return out


def find_evidence(question: str, records: list[dict], top_k: int = 4) -> list[dict]:
    from backend.app.services.vector_service import get_embedding_model

    sents = _sentences(records)
    if not sents:
        return []
    model = get_embedding_model()
    q_vec = model.encode([question], normalize_embeddings=True)[0]
    s_vecs = model.encode([s["text"] for s in sents], normalize_embeddings=True)
    scored = sorted(((float(v @ q_vec), s) for v, s in zip(s_vecs, sents)), key=lambda x: x[0], reverse=True)
    return [{**s, "score": round(score, 3)} for score, s in scored[:top_k] if score >= RELEVANCE_THRESHOLD]


# ------------------------------------------------------------ 4. local LLM
@lru_cache(maxsize=1)
def get_llm():
    import torch
    from transformers import pipeline

    return pipeline("text-generation", model=QA_MODEL, dtype=torch.bfloat16)


def _known_terms(records: list[dict]) -> set[str]:
    terms = set()
    for r in records:
        e = r["entities"]
        terms |= {t.lower() for t in e.get("diagnoses", []) + e.get("symptoms", []) + e.get("medications", [])}
        terms |= {a["substance"].lower() for a in e.get("allergies", [])}
    return terms | set(ALL_DRUGS)


_STOPWORDS = {"which", "there", "their", "about", "would", "could", "should", "these", "those", "other",
              "patient", "patients", "record", "records", "state", "states", "evidence", "since", "while",
              "being", "having", "after", "before", "where", "taking", "takes", "given"}


def _content_overlap(answer: str, evidence_text: str) -> float:
    """Share of the answer's meaningful words (5+ letters, compared by 5-letter stem) found in the evidence."""
    stems = lambda t: {w[:5] for w in re.findall(r"[a-z]{5,}", t.lower()) if w not in _STOPWORDS}
    words = stems(answer)
    return 1.0 if not words else len(words & stems(evidence_text)) / len(words)


MIN_OVERLAP = float(os.getenv("QA_MIN_OVERLAP", "0.75"))


def grounded(answer: str, evidence: list[dict], records: list[dict]) -> bool:
    """Reject answers that add words, drugs, conditions or numbers that are not in the evidence."""
    ev = " ".join(e["text"].lower() + " " + e["source"].lower() for e in evidence)
    a = answer.lower()
    if "does not state" not in a and _content_overlap(a, ev) < MIN_OVERLAP:
        return False
    for term in _known_terms(records):
        if re.search(rf"\b{re.escape(term)}\b", a) and term not in ev:
            return False
    for num in re.findall(r"\b\d+(?:\.\d+)?\b", a):
        if num not in ev and not re.fullmatch(r"r?\d", num):
            if not any(num in e["source"] for e in evidence) and not any(num == str(e["record_id"]) for e in evidence):
                return False
    return True


def _llm_answer(question: str, evidence: list[dict]) -> str:
    text = "\n".join(f"[R{e['record_id']}, {e['source']}] {e['text']}" for e in evidence)
    msgs = [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Evidence:\n{text}\n\nQuestion: {question}"}]
    out = get_llm()(msgs, max_new_tokens=90, do_sample=False)[0]["generated_text"][-1]["content"].strip()
    # small models sometimes echo half a citation at the start: "City General, 2026-01-15] ..."
    out = re.sub(r"^\[?[^\[\]]{0,80}\]\s*", "", out) if re.match(r"^\[?[^\[\]]{0,80}\]", out) else out
    return out.strip().strip("[]").strip()


# ------------------------------------------------------------------ public
def answer_question(question: str, summary: dict, records: list[dict], patient: dict | None = None,
                    use_llm: bool | None = None) -> dict:
    question = question.strip()
    if not question:
        return _answer("Please type a question.", "none")
    direct = _direct_answer(question, summary, patient or {})
    if direct:
        return direct

    evidence = find_evidence(question, records)
    if not evidence:
        return _answer("Not documented: no note in the accessible records mentions this.", "retrieval")

    if re.match(r"\s*why\b", question, re.I) and not any(CAUSAL_WORDS.search(e["text"]) for e in evidence):
        return _answer("The record does not state the reason. The most relevant note is shown below.",
                       "retrieval", evidence)

    if use_llm is None:
        use_llm = USE_LLM
    if use_llm:
        try:
            text = _llm_answer(question, evidence)
            if text and grounded(text, evidence, records):
                return _answer(text, "local LLM", evidence)
        except Exception as exc:  # model missing / out of memory -> fall back to the evidence
            return _answer(f"(LLM unavailable: {exc.__class__.__name__}) Most relevant notes are shown below.",
                           "retrieval", evidence)
    return _answer("Most relevant notes from the record are shown below.", "retrieval", evidence)
