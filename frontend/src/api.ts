import type { Analytics, AnalyzeResponse, RagResponse, RecordsResponse } from "./types";

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/health/"),
  analyzeNote: (clinical_note: string) =>
    request<AnalyzeResponse>("/extract/from-note", {
      method: "POST",
      body: JSON.stringify({ clinical_note }),
    }),
  rag: (query: string) =>
    request<RagResponse>("/rag/", { method: "POST", body: JSON.stringify({ query }) }),
  records: (params: { diagnosis?: string; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.diagnosis) q.set("diagnosis", params.diagnosis);
    q.set("limit", String(params.limit ?? 50));
    return request<RecordsResponse>(`/records/?${q}`);
  },
  analytics: () => request<Analytics>("/analytics/summary"),
};
