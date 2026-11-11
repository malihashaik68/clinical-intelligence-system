import { useState } from "react";
import { api } from "../api";
import type { RagResponse } from "../types";
import { SeverityBadge } from "./SeverityBadge";

export function SimilarCases() {
  const [query, setQuery] = useState("Elderly patient with shortness of breath and fatigue");
  const [result, setResult] = useState<RagResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask() {
    setLoading(true);
    setError(null);
    try {
      setResult(await api.rag(query));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="stack">
      <section className="card">
        <h2>Ask about similar past cases (RAG)</h2>
        <p className="muted">
          Finds the most similar stored notes with vector search (ChromaDB), then a local LLM
          (TinyLlama) writes a one-sentence summary. Facts come from the retrieved record.
        </p>
        <div className="row">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
            aria-label="Question"
          />
          <button className="primary" onClick={ask} disabled={loading || !query.trim()}>
            {loading ? "Searching…" : "Ask"}
          </button>
        </div>
        {error && <p className="error">Request failed: {error}</p>}
      </section>

      {result && (
        <>
          <section className="card">
            <div className="row spread">
              <h2>Answer</h2>
              {result.summary_source && (
                <span className="muted">
                  summary written by {result.summary_source === "llm" ? "the local LLM" : "a template (LLM output rejected)"}
                </span>
              )}
            </div>
            <pre className="answer">{result.generated_answer}</pre>
            <p className="muted small">Decision support only, not medical advice.</p>
          </section>
          <section className="card">
            <h2>Retrieved records</h2>
            {result.matches.length === 0 && <p className="muted">No stored records yet. Analyse a few notes first.</p>}
            {result.matches.map((m) => (
              <div key={m.record_id} className="subcard">
                <div className="row spread">
                  <strong>Record #{m.record_id}</strong>
                  <div className="row">
                    {m.severity && m.severity !== "unknown" && <SeverityBadge level={m.severity} />}
                    <span className="muted">distance {m.distance?.toFixed(3)}</span>
                  </div>
                </div>
                <p>{m.clinical_note}</p>
                <p className="muted">Diagnoses: {m.diagnoses || "–"} · Symptoms: {m.symptoms || "–"}</p>
              </div>
            ))}
          </section>
        </>
      )}
    </div>
  );
}
