import { useEffect, useState } from "react";
import { api, API_URL } from "./api";
import { NoteAnalyzer } from "./components/NoteAnalyzer";
import { RecordsAndAnalytics } from "./components/RecordsAndAnalytics";
import { SimilarCases } from "./components/SimilarCases";

type Tab = "analyze" | "similar" | "records";

const TABS: { id: Tab; label: string }[] = [
  { id: "analyze", label: "Note analysis" },
  { id: "similar", label: "Similar cases (RAG)" },
  { id: "records", label: "Records & analytics" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("analyze");
  const [online, setOnline] = useState<boolean | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    api.health().then(() => setOnline(true)).catch(() => setOnline(false));
  }, []);

  return (
    <div className="app">
      <header>
        <div>
          <h1>Clinical Intelligence</h1>
          <p>BERT entity extraction · RxNorm / OpenFDA / PubMed grounding · RAG over past cases</p>
        </div>
        <span className={`status ${online ? "ok" : online === false ? "down" : ""}`}>
          {online === null ? "connecting…" : online ? "backend online" : `backend offline (${API_URL})`}
        </span>
      </header>
      <nav>
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>
      <main>
        {/* Keep the analyser mounted so its result survives tab switches. */}
        <div hidden={tab !== "analyze"}>
          <NoteAnalyzer onSaved={() => setRefreshKey((k) => k + 1)} />
        </div>
        {tab === "similar" && <SimilarCases />}
        {tab === "records" && <RecordsAndAnalytics refreshKey={refreshKey} />}
      </main>
    </div>
  );
}
