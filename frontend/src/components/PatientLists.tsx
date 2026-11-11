import { useEffect, useState } from "react";
import { api } from "../api";
import type { PatientCard } from "../types";

function where(p: PatientCard) {
  return Object.entries(p.records_at).map(([h, n]) => `${h} (${n})`).join(", ") || "–";
}

function Row({ p, onOpen, extra }: { p: PatientCard; onOpen: (id: number) => void; extra?: string }) {
  return (
    <div className="subcard row spread">
      <div>
        <strong>{p.full_name}</strong> · {p.age} y · {p.sex} · <code>{p.health_id}</code>
        <div className="muted small">Records at: {where(p)}{extra ? ` · ${extra}` : ""}</div>
      </div>
      <button onClick={() => onOpen(p.id)}>Open</button>
    </div>
  );
}

export function MyPatients({ hospital, onOpen }: { hospital: string; onOpen: (id: number) => void }) {
  const [patients, setPatients] = useState<PatientCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.myPatients().then(setPatients).catch((e) => setError(String(e.message ?? e)));
  }, []);
  return (
    <section className="card">
      <h2>Patients at {hospital}</h2>
      {error && <p className="error">{error}</p>}
      {patients?.length === 0 && <p className="muted">No patients yet. Use Find a patient.</p>}
      {patients?.map((p) => <Row key={p.id} p={p} onOpen={onOpen} />)}
    </section>
  );
}

export function FindPatient({ onOpen }: { onOpen: (id: number) => void }) {
  const [healthId, setHealthId] = useState("HID-4821-7730");
  const [name, setName] = useState("");
  const [dob, setDob] = useState("");
  const [results, setResults] = useState<PatientCard[] | null>(null);

  async function search(e: React.FormEvent) {
    e.preventDefault();
    setResults(await api.search(healthId, name, dob));
  }

  return (
    <section className="card">
      <h2>Find a patient</h2>
      <p className="muted">
        The network index shows who the patient is and where records exist, not the records themselves.
      </p>
      <form onSubmit={search} className="row">
        <input placeholder="Health ID" value={healthId} onChange={(e) => setHealthId(e.target.value)} aria-label="Health ID" />
        <input placeholder="…or name" value={name} onChange={(e) => setName(e.target.value)} aria-label="Name" />
        <input type="date" value={dob} onChange={(e) => setDob(e.target.value)} aria-label="Date of birth" className="date" />
        <button className="primary">Search</button>
      </form>
      {results?.length === 0 && <p className="muted">No matching patient.</p>}
      {results?.map((p) => <Row key={p.id} p={p} onOpen={onOpen} extra={`match: ${p.match}`} />)}
    </section>
  );
}
