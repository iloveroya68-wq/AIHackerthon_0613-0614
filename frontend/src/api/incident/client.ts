import type { PredictionRequest, EnginePredictionResult, BriefingResult } from "@/types/contracts";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body != null ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    const message = typeof detail?.detail === "string" ? detail.detail : res.statusText;
    throw Object.assign(new Error(message), { status: res.status, detail });
  }
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw Object.assign(new Error(res.statusText), { status: res.status });
  return res.json() as Promise<T>;
}

export const incidentClient = {
  createPrediction: (req: PredictionRequest) =>
    post<EnginePredictionResult>("/api/v1/predictions/", req),

  getPrediction: (id: string) =>
    get<EnginePredictionResult>(`/api/v1/predictions/${id}/`),

  createBriefing: (predictionId: string) =>
    post<BriefingResult>(`/api/v1/predictions/${predictionId}/briefing/`),
};
