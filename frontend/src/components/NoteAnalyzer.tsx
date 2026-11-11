import { useState } from "react";
import { api } from "../api";
import type { AnalyzeResponse } from "../types";
import { SeverityBadge } from "./SeverityBadge";

const SAMPLES = [
  "58-year-old female with a history of hypertension and type 2 diabetes presents with chest pain and shortness of breath for two days. She reports fatigue and dizziness. Current medications include metformin 500 mg twice daily and lisinopril 10 mg daily. Started aspirin 81 mg.",
  "Patient diagnosed with pneumonia. Complains of fever, cough and nausea. Prescribed amoxicillin 500 mg three times daily and ibuprofen as needed.",
  "History of asthma and depression. Presents with headache and abdominal pain. Takes albuterol inhaler and sertraline 50 mg.",
];

function firstSentence(text: string | undefined, max = 220): string {
  if (!text) return "";
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

export function NoteAnalyzer({ onSaved }: { onSaved: () => void }) {
  const [note, setNote] = useState(SAMPLES[0]);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function analyze() {
    setLoading(true);
    setError(null);
    try {
      setResult(await api.analyzeNote(note));
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const e = result?.extracted_entities;
  const ctx = result?.api_results.structured_context;

  return (
    <div className="stack">
      <section className="card">
        <h2>Clinical note</h2>
        <textarea
          value={note}
          onChange={(ev) => setNote(ev.target.value)}
          rows={6}
          placeholder="Paste a physician note…"
          aria-label="Clinical note"
        />
        <div className="row">
          <button className="primary" onClick={analyze} disabled={loading || !note.trim()}>
            {loading ? "Analysing… (about 30 s)" : "Analyse note"}
          </button>
          <span className="muted">Samples:</span>
          {SAMPLES.map((s, i) => (
            <button key={i} className="ghost" onClick={() => setNote(s)}>
              Note {i + 1}
            </button>
          ))}
        </div>
        {error && <p className="error">Request failed: {error}</p>}
      </section>

      {result && e && ctx && (
        <>
          <section className="card">
            <div className="row spread">
              <h2>Extracted entities</h2>
              <div className="row">
                <SeverityBadge level={result.severity.level} />
                <span className="muted">Saved as record #{result.database.record_id}</span>
              </div>
            </div>
            {result.severity.reasons.length > 0 && (
              <ul className="reasons">
                {result.severity.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
            <div className="grid3">
              <div>
                <h3>Medications</h3>
                {e.medication_details.map((m) => (
                  <span key={m.name} className="chip chip-med">
                    {m.name}
                    {m.dosage && <small> · {m.dosage}</small>}
                  </span>
                ))}
                {e.medication_details.length === 0 && <p className="muted">None found</p>}
              </div>
              <div>
                <h3>Symptoms</h3>
                {e.symptoms.map((s) => (
                  <span key={s} className="chip chip-sym">{s}</span>
                ))}
                {e.symptoms.length === 0 && <p className="muted">None found</p>}
              </div>
              <div>
                <h3>Diagnoses</h3>
                {e.diagnoses.map((d) => (
                  <span key={d} className="chip chip-dx">{d}</span>
                ))}
                {e.diagnoses.length === 0 && <p className="muted">None found</p>}
              </div>
            </div>
            <details>
              <summary>Model output ({e.raw_entities.length} raw entities)</summary>
              <table>
                <thead>
                  <tr><th>Text</th><th>Label</th><th>Source</th><th>Confidence</th></tr>
                </thead>
                <tbody>
                  {e.raw_entities.map((r, i) => (
                    <tr key={i}>
                      <td>{r.text}</td>
                      <td>{r.entity_group}</td>
                      <td>{r.source}</td>
                      <td>{r.score != null ? r.score.toFixed(2) : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </section>

          <section className="card">
            <h2>Drug information (RxNorm · OpenFDA)</h2>
            <div className="grid2">
              {ctx.medications.map((m) => {
                const label = m.openfda.results[0];
                return (
                  <div key={m.input_name} className="subcard">
                    <div className="row spread">
                      <strong>{m.input_name}</strong>
                      <span className="muted">
                        RxCUI {m.rxnorm.rxcui ?? "not found"} · {m.openfda.count} FDA label(s)
                      </span>
                    </div>
                    {label ? (
                      <>
                        <p><b>Indications:</b> {firstSentence(label.indications_and_usage[0])}</p>
                        <p><b>Warnings:</b> {firstSentence(label.warnings[0]) || "–"}</p>
                      </>
                    ) : (
                      <p className="muted">No FDA label found.</p>
                    )}
                  </div>
                );
              })}
            </div>
          </section>

          <section className="card">
            <h2>Supporting literature (PubMed)</h2>
            <ul className="lit">
              {ctx.literature.map((l) => (
                <li key={l.query}>
                  <span className="muted">{l.query}:</span>{" "}
                  {l.results[0] ? (
                    <a href={`https://pubmed.ncbi.nlm.nih.gov/${l.results[0].pmid}/`} target="_blank" rel="noreferrer">
                      {l.results[0].title}
                    </a>
                  ) : (
                    <span className="muted">no article</span>
                  )}
                  {l.results[0] && <small className="muted"> ({l.results[0].source}, {l.results[0].pubdate})</small>}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
