import type { RiskForecastResult } from "@/types/contracts";
import { SEA_AREAS } from "./seaAreas";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${BASE}${path}`, location.href);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const res = await fetch(url.toString());
  if (!res.ok) throw Object.assign(new Error(res.statusText), { status: res.status });
  return res.json() as Promise<T>;
}

export const riskClient = {
  getRiskForecast: (params?: { area_name?: string; time_range_start?: string }) => {
    const area = params?.area_name ?? "";
    const bbox = SEA_AREAS[area]?.bbox.join(",");
    return get<RiskForecastResult>("/api/v1/risk/forecast/", {
      ...(area && { area_name: area }),
      ...(bbox && { bbox }),
      vessel_types: "소형어선,표준어선",
      ...(params?.time_range_start && { time_range_start: params.time_range_start }),
    });
  },

  getRiskForecastBatch: async () => {
    const entries = await Promise.all(
      Object.keys(SEA_AREAS).map(async (areaName) => [
        areaName,
        await riskClient.getRiskForecast({ area_name: areaName }),
      ] as const),
    );
    return Object.fromEntries(entries) as Record<string, RiskForecastResult>;
  },
};
