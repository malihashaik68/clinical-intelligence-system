import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { Alert, Analysis, Answer, LogEntry, PatientView } from "../types";
import { SeverityBadge } from "./SeverityBadge";

type Tab = "summary" | "ask" | "note" | "history" | "card" | "log";
const TABS: [Tab, string][] = [
  ["summary", "Emergency summary"], ["ask", "Ask about this patient"], ["note", "Add visit note"],
  ["history", "Visit history"], ["card", "Emergency card & FHIR"], ["log", "Access log"],
];
const EXAMPLES = ["Any allergies?", "Is the patient on blood thinners?", "What medications are current?",
                  "Can I give amoxicillin?", "What happened at the last visit?", "Does the patient smoke?"];

function Alerts({ alerts }: { alerts: Alert[] }) {
  return (
    <>
      {alerts.map((a) => (
        <div key={a.message} className={`alert alert-${a.severity}`}>
          <b>{a.type}</b>: {a.message}
          <div className="small">Sources: {a.sources.join(" · ")}</div>
        </div>
      ))}
    </>
  );
}

function AccessPanel({ id, partial, onGranted }: { id: number; partial: boolean; onGranted: () => void }) {
  const [sms, setSms] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  return (
    <section className="card locked">
      <h2>🔒 {partial ? "Records at other hospitals are locked" : "No access to this patient"}</h2>
      <div className="grid2">
        <div>
          <h3>Patient consent</h3>
          <p className="small muted">The patient approves with a code sent to their phone (7 days).</p>
          <button onClick={async () => setSms((await api.requestConsent(id)).simulated_sms_code)}>
            Send code to patient
          </button>
          {sms && (
            <div className="stack" style={{ marginTop: 8 }}>
              <p className="info">📱 Simulated SMS to patient: your code is <b>{sms}</b></p>
              <div className="row">
                <input placeholder="Code from the patient" value={code} onChange={(e) => setCode(e.target.value)}
                       aria-label="Consent code" />
                <button className="primary" onClick={async () => {
                  try { await api.confirmConsent(id, code); onGranted(); }
                  catch { setMsg("Wrong or expired code."); }
                }}>Confirm consent</button>
              </div>
            </div>
          )}
        </div>
        <div>
          <h3>🚨 Emergency access</h3>
          <p className="small muted">When the patient can't consent. 24 h, logged, patient and home hospital notified.</p>
          <div className="row">
            <input placeholder="Reason, e.g. unconscious after collapse" value={reason}
                   onChange={(e) => setReason(e.target.value)} aria-label="Emergency reason" />
            <button className="danger" onClick={async () => {
              try { await api.emergency(id, reason); onGranted(); }
              catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
            }}>Break the glass</button>
          </div>
        </div>
      </div>
      {msg && <p className="error">{msg}</p>}
    </section>
  );
}

function SummaryTab({ v }: { v: PatientView }) {
  const s = v.summary;
  return (
    <div className="stack">
      {s.alerts.length > 0 && <section className="card"><h2>⚠️ Safety alerts</h2><Alerts alerts={s.alerts} /></section>}
      <div className="grid-summary">
        <section className="card">
          <h3>Allergies</h3>
          {s.allergies.map((a) => (
            <div key={a.substance} className="alert alert-high">
              <b>{a.substance}</b>{a.reaction ? ` (${a.reaction})` : ""}
              <div className="small">Recorded at {a.hospital}, {a.date}</div>
            </div>
          ))}
          {!s.allergies.length && <p className={s.no_known_allergies ? "ok" : "muted"}>
            {s.no_known_allergies ? "No known drug allergies" : "No allergy information recorded"}</p>}
          <h3 style={{ marginTop: 16 }}>Conditions</h3>
          <ul>{s.conditions.map((c) => <li key={c.name}><b>{c.name}</b> <small className="muted">since {c.first_seen}</small></li>)}</ul>
          <p>Latest visit priority: <SeverityBadge level={s.latest_severity ?? undefined} /></p>
        </section>
        <section className="card">
          <h3>Current medications</h3>
          <table>
            <thead><tr><th>Medication</th><th>Dose</th><th>Last noted</th><th>Hospital</th></tr></thead>
            <tbody>
              {s.current_medications.map((m) => (
                <tr key={m.name}><td><b>{m.name}</b></td><td>{m.dosage ?? "–"}</td><td>{m.last_seen}</td><td>{m.hospital}</td></tr>
              ))}
              {!s.current_medications.length && <tr><td colSpan={4} className="muted">None recorded</td></tr>}
            </tbody>
          </table>
          {s.older_medications.length > 0 && (
            <p className="small muted">Older (not mentioned in the last year): {s.older_medications.map((m) => m.name).join(", ")}</p>
          )}
        </section>
      </div>
    </div>
  );
}

function AskTab({ id }: { id: number }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [chat, setChat] = useState<[string, Answer][]>([]);

  async function ask(question: string) {
    if (!question.trim()) return;
    setBusy(true);
    try {
      const a = await api.ask(id, question);
      setChat((c) => [[question, a], ...c]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card stack">
      <p className="muted">
        Answers come only from this patient's accessible records, with sources. Common questions are answered from
        the data; others use the local LLM, checked against the notes.
      </p>
      <div className="row">{EXAMPLES.map((e) => <button key={e} className="ghost" onClick={() => { setQ(e); ask(e); }}>{e}</button>)}</div>
      <form className="row" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask a question" aria-label="Question" />
        <button className="primary" disabled={busy}>{busy ? "Searching…" : "Ask"}</button>
      </form>
      {chat.map(([question, a], i) => (
        <div key={i} className="subcard">
          <b>Q: {question}</b>
          <pre className="answer">{a.answer}</pre>
          <div className="small muted">Answered by: {a.method}</div>
          {a.llm_note && <div className="small muted">ℹ️ {a.llm_note}</div>}
          {a.evidence.length > 0 && (
            <details><summary>Source sentences</summary>
              <ul>{a.evidence.map((e, j) => <li key={j}>“{e.text}” <small className="muted">(record #{e.record_id}, {e.source})</small></li>)}</ul>
            </details>
          )}
        </div>
      ))}
    </section>
  );
}

function NoteTab({ id, before, onSaved }: { id: number; before: Alert[]; onSaved: () => Promise<PatientView> }) {
  const [note, setNote] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ a: Analysis; id: number; newAlerts: Alert[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const a = await api.addNote(id, note, date);
      const after = await onSaved();
      const old = new Set(before.map((x) => x.message));
      setResult({ a, id: a.database.record_id, newAlerts: after.summary.alerts.filter((x) => !old.has(x.message)) });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const e = result?.a.extracted_entities;
  return (
    <section className="card stack">
      <p className="muted">The note analyser extracts medications, doses, symptoms, diagnoses and allergies, then
        checks the combined history for new safety alerts.</p>
      <textarea rows={5} value={note} onChange={(ev) => setNote(ev.target.value)} aria-label="Clinical note"
                placeholder="e.g. Fever and cough. Prescribed amoxicillin 500 mg three times daily." />
      <div className="row">
        <input type="date" value={date} onChange={(ev) => setDate(ev.target.value)} className="date" aria-label="Visit date" />
        <button className="primary" disabled={busy || !note.trim()} onClick={save}>
          {busy ? "Analysing…" : "Analyse and save"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {result && e && (
        <>
          <p className="ok">Saved as record #{result.id} · priority <SeverityBadge level={result.a.severity.level} /></p>
          <div className="grid4">
            <div><h3>Medications</h3>{e.medication_details.map((m) => <span key={m.name} className="chip chip-med">{m.name}{m.dosage && <small> · {m.dosage}</small>}</span>)}</div>
            <div><h3>Symptoms</h3>{e.symptoms.map((s) => <span key={s} className="chip chip-sym">{s}</span>)}</div>
            <div><h3>Diagnoses</h3>{e.diagnoses.map((d) => <span key={d} className="chip chip-dx">{d}</span>)}</div>
            <div><h3>Allergies</h3>{e.allergies.map((a) => <span key={a.substance} className="chip chip-allergy">{a.substance}</span>)}</div>
          </div>
          {result.newAlerts.length > 0 && <><h2>⚠️ New safety alerts caused by this note</h2><Alerts alerts={result.newAlerts} /></>}
        </>
      )}
    </section>
  );
}

function CardTab({ id, healthId }: { id: number; healthId: string }) {
  const [img, setImg] = useState<string | null>(null);
  useEffect(() => {
    let url: string | null = null;
    api.card(id).then((u) => { url = u; setImg(u); });
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [id]);

  async function downloadFhir() {
    const blob = new Blob([JSON.stringify(await api.fhir(id), null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `fhir_${healthId}.json`;
    a.click();
  }

  return (
    <section className="card stack">
      <p className="muted">A printable card with the life-critical facts and a QR code. It works with no connection
        between hospitals.</p>
      {img && <img src={img} alt="Emergency card" className="emergency-card" />}
      <div className="row">
        {img && <a className="button" href={img} download={`emergency_card_${healthId}.png`}>Download card (PNG)</a>}
        <button onClick={downloadFhir}>Export history as HL7 FHIR (JSON)</button>
      </div>
    </section>
  );
}

function LogTab({ id }: { id: number }) {
  const [log, setLog] = useState<LogEntry[]>([]);
  useEffect(() => { api.accessLog(id).then(setLog); }, [id]);
  return (
    <section className="card">
      <p className="muted">Every view, question, consent and emergency access is recorded.</p>
      <table>
        <thead><tr><th>Time (UTC)</th><th>Practitioner</th><th>Hospital</th><th>Action</th><th>Detail</th></tr></thead>
        <tbody>{log.map((l, i) => (
          <tr key={i} className={l.action === "EMERGENCY_ACCESS" ? "row-emergency" : ""}>
            <td className="small">{l.time.replace("T", " ").slice(0, 19)}</td><td>{l.practitioner}</td>
            <td>{l.hospital}</td><td><b>{l.action}</b></td><td className="small">{l.detail}</td>
          </tr>))}
        </tbody>
      </table>
    </section>
  );
}

export function PatientPage({ id, onBack }: { id: number; onBack: () => void }) {
  const [view, setView] = useState<PatientView | null>(null);
  const [denied, setDenied] = useState(false);
  const [tab, setTab] = useState<Tab>("summary");

  const load = useCallback(async () => {
    try {
      const v = await api.patient(id);
      setView(v);
      setDenied(false);
      return v;
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) setDenied(true);
      throw e;
    }
  }, [id]);

  useEffect(() => { load().catch(() => undefined); }, [load]);

  if (denied) {
    return (
      <div className="stack">
        <button onClick={onBack} className="ghost">← Back</button>
        <AccessPanel id={id} partial={false} onGranted={() => load()} />
      </div>
    );
  }
  if (!view) return <p className="muted">Loading…</p>;
  const p = view.patient;
  const a = view.access;

  return (
    <div className="stack">
      <button onClick={onBack} className="ghost back">← Back</button>
      <section className="card">
        <h1>{p.full_name}</h1>
        <p><b>{p.age} y · {p.sex} · Blood type {p.blood_type || "?"} · {p.health_id}</b><br />
          📞 Emergency contact: {p.emergency_contact || "–"}</p>
        {a.grant_kind === "emergency" && <p className="alert alert-high">🚨 Emergency access active until {a.grant_expires} UTC: logged and reported.</p>}
        {a.grant_kind === "consent" && <p className="ok">✅ Patient consent: records from all hospitals visible until {a.grant_expires} UTC.</p>}
        <p className="small muted">Records exist at: {Object.entries(p.records_at).map(([h, n]) => `${h} (${n})`).join(", ")}</p>
      </section>
      {view.hidden_records_at_other_hospitals > 0 && (
        <>
          <p className="alert alert-medium">{view.hidden_records_at_other_hospitals} record(s) at other hospitals are not
            visible. Allergies or medications may be missing.</p>
          <AccessPanel id={id} partial onGranted={() => load()} />
        </>
      )}
      <nav className="subnav">
        {TABS.map(([t, label]) => <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>{label}</button>)}
      </nav>
      {tab === "summary" && <SummaryTab v={view} />}
      {tab === "ask" && <AskTab id={id} />}
      {tab === "note" && <NoteTab id={id} before={view.summary.alerts} onSaved={load} />}
      {tab === "history" && (
        <section className="card">{view.summary.timeline.map((t) => (
          <details key={t.record_id}>
            <summary>{t.date} · {t.hospital} · <SeverityBadge level={t.severity} /> · {t.author}</summary>
            <p>{t.note}</p>
            <p className="small muted">Diagnoses: {t.diagnoses.join(", ") || "–"} · Medications: {t.medications.join(", ") || "–"}</p>
          </details>))}
        </section>
      )}
      {tab === "card" && <CardTab id={id} healthId={p.health_id} />}
      {tab === "log" && <LogTab id={id} />}
    </div>
  );
}
