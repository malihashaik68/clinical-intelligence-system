import type { AccessStatus, Analysis, Answer, LogEntry, PatientCard, PatientView, User } from "./types";

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

let token: string | null = sessionStorage.getItem("ci_token");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, String(detail));
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown = {}) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<{ status: string }>("/health/"),

  async login(username: string, password: string): Promise<User> {
    const res = await post<{ token: string; user: User }>("/auth/login", { username, password });
    token = res.token;
    sessionStorage.setItem("ci_token", res.token);
    return res.user;
  },
  me: () => request<User>("/auth/me"),
  logout() {
    token = null;
    sessionStorage.removeItem("ci_token");
  },
  hasToken: () => token !== null,

  myPatients: () => request<PatientCard[]>("/patients/"),
  search: (healthId: string, name: string, dob: string) => {
    const q = new URLSearchParams({ health_id: healthId, name });
    if (dob) q.set("dob", dob);
    return request<PatientCard[]>(`/patients/search?${q}`);
  },
  patient: (id: number) => request<PatientView>(`/patients/${id}/summary`),
  requestConsent: (id: number) =>
    post<{ message: string; simulated_sms_code: string }>(`/patients/${id}/consent/request`),
  confirmConsent: (id: number, code: string) =>
    post<{ granted: boolean; access: AccessStatus }>(`/patients/${id}/consent/confirm`, { code }),
  emergency: (id: number, reason: string) => post(`/patients/${id}/emergency-access`, { reason }),
  ask: (id: number, question: string) => post<Answer>(`/patients/${id}/ask`, { question }),
  addNote: (id: number, clinical_note: string, visit_date: string) =>
    post<Analysis & { database: { record_id: number } }>(`/patients/${id}/notes`, {
      clinical_note,
      visit_date,
      literature: false,
    }),
  accessLog: (id: number) => request<LogEntry[]>(`/patients/${id}/access-log`),
  fhir: (id: number) => request<object>(`/patients/${id}/fhir`),
  async card(id: number): Promise<string> {
    const res = await fetch(`${API_URL}/patients/${id}/emergency-card`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    return URL.createObjectURL(await res.blob());
  },
  analyze: (clinical_note: string, literature: boolean) =>
    post<Analysis>("/extract/analyze", { clinical_note, literature }),
};
