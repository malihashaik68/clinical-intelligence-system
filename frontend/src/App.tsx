import { useEffect, useState } from "react";
import { api } from "./api";
import { Login } from "./components/Login";
import { NoteAnalyzer } from "./components/NoteAnalyzer";
import { PatientPage } from "./components/PatientPage";
import { FindPatient, MyPatients } from "./components/PatientLists";
import type { User } from "./types";

type Page = "mine" | "find" | "analyser";

const PAGES: [Page, string][] = [["mine", "My patients"], ["find", "Find a patient"], ["analyser", "Note analyser"]];

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(api.hasToken());
  const [page, setPage] = useState<Page>("mine");
  const [patientId, setPatientId] = useState<number | null>(null);

  useEffect(() => {
    if (!api.hasToken()) return;
    api.me().then(setUser).catch(() => api.logout()).finally(() => setChecking(false));
  }, []);

  if (checking) return <p className="muted app">Loading…</p>;
  if (!user) return <div className="app"><Login onLogin={setUser} /></div>;

  return (
    <div className="app">
      <header>
        <div>
          <h1>Clinical Intelligence</h1>
          <p>{user.full_name} · {user.role} · 🏥 {user.hospital_name}</p>
        </div>
        <button className="ghost" onClick={() => { api.logout(); setUser(null); setPatientId(null); }}>Log out</button>
      </header>
      <nav>
        {PAGES.map(([p, label]) => (
          <button key={p} className={page === p && patientId === null ? "active" : ""}
                  onClick={() => { setPage(p); setPatientId(null); }}>{label}</button>
        ))}
      </nav>
      <main>
        {patientId !== null ? (
          <PatientPage id={patientId} onBack={() => setPatientId(null)} />
        ) : page === "mine" ? (
          <MyPatients hospital={user.hospital_name} onOpen={setPatientId} />
        ) : page === "find" ? (
          <FindPatient onOpen={setPatientId} />
        ) : (
          <NoteAnalyzer />
        )}
      </main>
      <footer className="muted small">Fictional demo data · decision support only, not medical advice</footer>
    </div>
  );
}
