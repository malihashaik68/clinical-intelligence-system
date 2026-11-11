import { useState } from "react";
import { api } from "../api";
import type { User } from "../types";

const DEMO = [
  { username: "dr.lee", name: "Dr. Sarah Lee", role: "Emergency physician", hospital: "Riverside Medical Center" },
  { username: "dr.rao", name: "Dr. Anita Rao", role: "Cardiologist", hospital: "City General Hospital" },
  { username: "dr.chen", name: "Dr. Michael Chen", role: "Primary care", hospital: "City General Hospital" },
];

export function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [username, setUsername] = useState("dr.lee");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogin(await api.login(username, password));
    } catch {
      setError("Invalid username or password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <section className="card">
        <h1>Clinical Intelligence</h1>
        <p className="muted">
          Private medical history for practitioners. Patients rarely carry their history; this app builds it from
          clinical notes and shares it across hospitals only with patient consent or a logged emergency access.
        </p>
        <form onSubmit={submit} className="stack">
          <label>
            Username
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                   autoComplete="current-password" />
          </label>
          <button className="primary" disabled={busy}>{busy ? "Logging in…" : "Log in"}</button>
          {error && <p className="error">{error}</p>}
        </form>
      </section>
      <section className="card">
        <h2>Demo accounts</h2>
        <p className="muted">Password for all: <code>demo1234</code>. All patients and notes are fictional.</p>
        <table>
          <thead><tr><th>Username</th><th>Name</th><th>Hospital</th></tr></thead>
          <tbody>
            {DEMO.map((d) => (
              <tr key={d.username} onClick={() => setUsername(d.username)} className="clickable">
                <td><code>{d.username}</code></td><td>{d.name}<br /><small className="muted">{d.role}</small></td>
                <td>{d.hospital}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">
          Try <b>dr.lee</b>: Find a patient → <code>HID-4821-7730</code> → emergency access.
        </p>
      </section>
    </div>
  );
}
