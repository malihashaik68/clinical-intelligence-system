import os
from functools import lru_cache

from backend.app.services.vector_service import search_similar_records

LLM_MODEL = os.getenv("RAG_LLM_MODEL", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
# Set RAG_USE_LLM=0 to skip generation (e.g. on a small machine); the answer is then
# built directly from the retrieved records.
USE_LLM = os.getenv("RAG_USE_LLM", "1") != "0"


@lru_cache(maxsize=1)
def get_generator():
    """Local LLM used to write the answer (downloads ~2.2 GB the first time)."""
    from transformers import pipeline

    return pipeline("text-generation", model=LLM_MODEL)


def _terms(match: dict) -> set:
    terms = set()
    for key in ("diagnoses", "symptoms", "medications"):
        terms |= {t.strip().lower() for t in (match.get(key) or "").split(",") if t.strip()}
    return terms


def build_context(matches):
    context_blocks = []

    for i, match in enumerate(matches, start=1):
        context_blocks.append(
            f"Record {i}:\n"
            f"Clinical Note: {match.get('clinical_note', '')}\n"
            f"Diagnoses: {match.get('diagnoses', '')}\n"
            f"Symptoms: {match.get('symptoms', '')}\n"
            f"Medications: {match.get('medications', '')}\n"
            f"Distance: {match.get('distance', '')}\n"
        )

    return "\n".join(context_blocks)


def is_grounded(sentence: str, top: dict, matches: list[dict]) -> bool:
    """Reject a sentence that names a diagnosis, symptom or drug from another
    retrieved case but not from the top case (a common small-LLM mix-up)."""
    text = sentence.lower()
    allowed = _terms(top)
    other_terms = set().union(*(_terms(m) for m in matches)) - allowed
    return not any(term in text for term in other_terms)


def llm_summary_sentence(query: str, top: dict) -> str:
    """Ask the local LLM for ONE sentence about the most similar case."""
    generator = get_generator()
    messages = [
        {"role": "system", "content": "You are a clinical assistant. Use only facts from the case. "
                                      "Answer in one sentence."},
        {"role": "user", "content": f"Most similar past case: {top.get('clinical_note', '')}\n\n"
                                    f"New patient: {query}\n\n"
                                    "In one sentence, what does the past case suggest for the new patient?"},
    ]
    prompt = generator.tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True)
    text = generator(prompt, max_new_tokens=70, do_sample=False, repetition_penalty=1.15,
                     return_full_text=False)[0]["generated_text"]
    first = text.strip().split("\n")[0]
    return first.split(". ")[0].rstrip(".") + "." if first else ""


def generate_rag_response(query: str, top_k: int = 3):
    retrieval_results = search_similar_records(query, top_k=top_k)
    matches = retrieval_results.get("matches", [])

    if not matches:
        return {
            "query": query,
            "matches": [],
            "generated_answer": "No similar clinical records were found."
        }

    top = matches[0]
    summary = "The query is most similar to a previously stored clinical case."
    summary_source = "template"
    if USE_LLM:
        try:
            sentence = llm_summary_sentence(query, top)
            if sentence and is_grounded(sentence, top, matches):
                summary, summary_source = sentence, "llm"
        except Exception:
            pass

    # Structured fields always come from the retrieved record, never from the LLM.
    generated_answer = (
        f"Summary: {summary}\n"
        f"Likely diagnosis: {top.get('diagnoses') or 'not identified'}\n"
        f"Key symptoms: {top.get('symptoms') or 'not identified'}\n"
        f"Relevant medications: {top.get('medications') or 'not identified'}"
    )

    return {
        "query": query,
        "matches": matches,
        "generated_answer": generated_answer,
        "summary_source": summary_source,
    }
