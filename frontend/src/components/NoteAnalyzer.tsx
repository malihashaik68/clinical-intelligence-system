import { useState } from "react";
import { api } from "../api";
import type { Analysis } from "../types";
import { SeverityBadge } from "./SeverityBadge";

const SAMPLE =
  "62-year-old woman with COPD and atrial fibrillation on apixaban 5 mg twice daily presents with shortness of " +
  "breath and chest tightness. Allergic to codeine (vomiting).";

function short(text: string | undefined, n = 220) {
  const t = (text ?? "").replace(/\s+/g, " ").trim();
  return t.length > n ? `${t.slice(0, n)}…` : t;
}

export function NoteAnalyzer() {
  const [note, setNote] = useState(SAMPLE);
  const [literature, setLiterature] = useState(true);
  const [result, setResult] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function analyse() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.analyze(note, literature));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const e = result?.extracted_entities;
  const ctx = result?.api_results.structured_context;
  return (
    <div className="stack">
      <section className="card stack">
        <h2>Note analyser</h2>
        <p className="muted">Analyse any clinical note without saving it: BERT entity extraction, allergies, severity,
          and grounding in RxNorm, OpenFDA and PubMed. The same engine builds patient histories.</p>
        <textarea rows={5} value={note} onChange={(ev) => setNote(ev.target.value)} aria-label="Clinical note" />
        <div className="row">
          <button className="primary" disabled={busy || !note.trim()} onClick={analyse}>
            {busy ? "Analysing… (10–30 s)" : "Analyse"}
          </button>
          <label className="row small"><input type="checkbox" checked={literature}
                 onChange={(ev) => setLiterature(ev.target.checked)} style={{ width: "auto" }} /> Include PubMed</label>
        </div>
        {error && <p className="error">{error}</p>}
      </section>
      {result && e && (
        <>
          <section className="card">
            <div className="row spread"><h2>Extracted</h2><SeverityBadge level={result.severity.level} /></div>
            {result.severity.reasons.length > 0 && <ul className="reasons">{result.severity.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
            <div className="grid4">
              <div><h3>Medications</h3>{e.medication_details.map((m) => <span key={m.name} className="chip chip-med">{m.name}{m.dosage && <small> · {m.dosage}</small>}</span>)}</div>
              <div><h3>Symptoms</h3>{e.symptoms.map((s) => <span key={s} className="chip chip-sym">{s}</span>)}</div>
              <div><h3>Diagnoses</h3>{e.diagnoses.map((d) => <span key={d} className="chip chip-dx">{d}</span>)}</div>
              <div><h3>Allergies</h3>{e.allergies.map((a) => <span key={a.substance} className="chip chip-allergy">{a.substance}{a.reaction && <small> · {a.reaction}</small>}</span>)}</div>
            </div>
          </section>
          {ctx && (
            <section className="card">
              <h2>Drug information (RxNorm · OpenFDA)</h2>
              <div className="grid2">{ctx.medications.map((m) => (
                <div key={m.input_name} className="subcard">
                  <b>{m.input_name}</b> <span className="muted">· RxCUI {m.rxnorm.rxcui ?? "not found"} · {m.openfda.count} FDA label(s)</span>
                  <p className="small">{short(m.openfda.results[0]?.indications_and_usage[0]) || "No FDA label found."}</p>
                </div>))}
              </div>
              {ctx.literature.length > 0 && <h2 style={{ marginTop: 16 }}>Literature (PubMed)</h2>}
              <ul className="lit">{ctx.literature.map((l) => l.results[0] && (
                <li key={l.query}><span className="muted">{l.query}:</span>{" "}
                  <a href={`https://pubmed.ncbi.nlm.nih.gov/${l.results[0].pmid}/`} target="_blank" rel="noreferrer">{l.results[0].title}</a></li>))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
