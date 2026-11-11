import { useEffect, useState } from "react";
import { api } from "../api";
import type { Analytics, StoredRecord } from "../types";
import { SeverityBadge } from "./SeverityBadge";

function BarList({ title, items }: { title: string; items: [string, number][] }) {
  const max = Math.max(1, ...items.map(([, n]) => n));
  return (
    <div className="subcard">
      <h3>{title}</h3>
      {items.length === 0 && <p className="muted">No data yet</p>}
      {items.map(([label, n]) => (
        <div key={label} className="bar-row">
          <span className="bar-label">{label}</span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(100 * n) / max}%` }} />
          </span>
          <span className="bar-value">{n}</span>
        </div>
      ))}
    </div>
  );
}

export function RecordsAndAnalytics({ refreshKey }: { refreshKey: number }) {
  const [records, setRecords] = useState<StoredRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<Analytics | null>(null);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      Promise.all([api.records({ diagnosis: filter || undefined }), api.analytics()])
        .then(([r, a]) => {
          setRecords(r.records);
          setTotal(r.total);
          setStats(a);
          setError(null);
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    }, 250);
    return () => clearTimeout(t);
  }, [filter, refreshKey]);

  const sev = stats?.severity_counts ?? {};

  return (
    <div className="stack">
      {error && <p className="error">Could not load data: {error}</p>}
      <section className="kpis">
        <div className="kpi"><span>{stats?.total_records ?? 0}</span>notes analysed</div>
        <div className="kpi kpi-high"><span>{sev.high ?? 0}</span>high priority</div>
        <div className="kpi kpi-medium"><span>{sev.medium ?? 0}</span>medium priority</div>
        <div className="kpi kpi-low"><span>{sev.low ?? 0}</span>low priority</div>
      </section>
      <section className="grid3">
        <BarList title="Top diagnoses" items={stats?.top_diagnoses ?? []} />
        <BarList title="Top symptoms" items={stats?.top_symptoms ?? []} />
        <BarList title="Top medications" items={stats?.top_medications ?? []} />
      </section>
      <section className="card">
        <div className="row spread">
          <h2>Stored records ({total})</h2>
          <input
            className="filter"
            placeholder="Filter by diagnosis, e.g. asthma"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            aria-label="Filter by diagnosis"
          />
        </div>
        <table>
          <thead>
            <tr><th>#</th><th>Priority</th><th>Diagnoses</th><th>Symptoms</th><th>Medications</th><th>Saved</th></tr>
          </thead>
          <tbody>
            {records.map((r) => (
              <tr key={r.id} title={r.clinical_note}>
                <td>{r.id}</td>
                <td><SeverityBadge level={r.extracted_entities.severity?.level} /></td>
                <td>{r.extracted_entities.diagnoses.join(", ") || "–"}</td>
                <td>{r.extracted_entities.symptoms.join(", ") || "–"}</td>
                <td>{r.extracted_entities.medications.join(", ") || "–"}</td>
                <td className="muted">{r.created_at ? new Date(r.created_at).toLocaleString() : "–"}</td>
              </tr>
            ))}
            {records.length === 0 && (
              <tr><td colSpan={6} className="muted">No records yet.</td></tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
