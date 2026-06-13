import type { PredictionRequest, EnginePredictionResult, BriefingResult } from "@/types/contracts";

import predictionResultRaw from "../../../../contracts/examples/engine_prediction_result_example.json";
import briefingResultRaw from "../../../../contracts/examples/briefing_result_example.json";

const predictionResult = predictionResultRaw as unknown as EnginePredictionResult;
const briefingResult = briefingResultRaw as unknown as BriefingResult;

function delay<T>(ms: number, value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

// ── Ellipse polygon (mirrors mock_engine.py logic) ─────────────────────────

function makeEllipse(
  cLon: number, cLat: number,
  aMajor: number, bMinor: number,
  driftDeg: number,
  n = 24,
): number[][] {
  const latScale = 1 / 111.0;
  const lonScale = 1 / (111.0 * Math.cos((cLat * Math.PI) / 180));
  const theta = (driftDeg * Math.PI) / 180;
  const coords: number[][] = [];
  for (let i = 0; i < n; i++) {
    const phi = (2 * Math.PI * i) / n;
    const eKm = aMajor * Math.cos(phi) * Math.sin(theta) + bMinor * Math.sin(phi) * (-Math.cos(theta));
    const nKm = aMajor * Math.cos(phi) * Math.cos(theta) + bMinor * Math.sin(phi) * Math.sin(theta);
    coords.push([
      parseFloat((cLon + eKm * lonScale).toFixed(6)),
      parseFloat((cLat + nKm * latScale).toFixed(6)),
    ]);
  }
  coords.push(coords[0]);
  return coords;
}

// ── Simulation constants ───────────────────────────────────────────────────

const SIM_HOURS = 24;
const BASE_RADII = [3.2, 5.3, 8.4];
const PROBS = [0.60, 0.80, 0.95];

function buildZoneFeatures(cLon: number, cLat: number, driftDeg: number, h: number) {
  const scale = Math.sqrt(h / 6.0);
  return BASE_RADII.map((r, idx) => {
    const rk = r * scale;
    const a = rk * 1.35;
    const b = rk * 0.85;
    return {
      type: "Feature" as const,
      properties: {
        priority: (idx + 1) as 1 | 2 | 3,
        cumulative_probability: PROBS[idx],
        area_km2: parseFloat((Math.PI * a * b).toFixed(1)),
        center_lon: parseFloat(cLon.toFixed(6)),
        center_lat: parseFloat(cLat.toFixed(6)),
        radius_km: parseFloat(rk.toFixed(2)),
      },
      geometry: {
        type: "Polygon" as const,
        coordinates: [makeEllipse(cLon, cLat, a, b, driftDeg)],
      },
    };
  });
}

// Takes the user's last_coordinate as origin so the amber marker and drift
// track always start from the same point.
function buildTimeSteps(
  result: EnginePredictionResult,
  requestOrigin?: { lat: number; lon: number },
): EnginePredictionResult {
  const dv = result.drift_vector;
  const dirRad = (dv.direction_deg * Math.PI) / 180;

  let originLat: number;
  let originLon: number;
  if (requestOrigin) {
    originLat = requestOrigin.lat;
    originLon = requestOrigin.lon;
  } else {
    const fc = result.predicted_center;
    const nm = dv.speed_knots * result.time_horizon_hours;
    const cosLat = Math.cos((fc.lat * Math.PI) / 180);
    originLat = fc.lat - (nm * Math.cos(dirRad)) / 60;
    originLon = fc.lon - (nm * Math.sin(dirRad)) / (60 * cosLat);
  }

  const cosLat = Math.cos((originLat * Math.PI) / 180);
  const dLatPerH = (dv.speed_knots * Math.cos(dirRad)) / 60;
  const dLonPerH = (dv.speed_knots * Math.sin(dirRad)) / (60 * cosLat);

  const time_steps = Array.from({ length: SIM_HOURS }, (_, i) => {
    const h = i + 1;
    const cLat = originLat + dLatPerH * h;
    const cLon = originLon + dLonPerH * h;
    return {
      hours: h,
      search_zones: { type: "FeatureCollection" as const, features: buildZoneFeatures(cLon, cLat, dv.direction_deg, h) },
      predicted_center: { lon: parseFloat(cLon.toFixed(6)), lat: parseFloat(cLat.toFixed(6)) },
      drift_distance_nm: parseFloat((dv.speed_knots * h).toFixed(3)),
    };
  });

  const finalLat = originLat + dLatPerH * SIM_HOURS;
  const finalLon = originLon + dLonPerH * SIM_HOURS;

  return {
    ...result,
    time_horizon_hours: SIM_HOURS,
    predicted_center: { lon: parseFloat(finalLon.toFixed(6)), lat: parseFloat(finalLat.toFixed(6)) },
    search_zones: { type: "FeatureCollection" as const, features: buildZoneFeatures(finalLon, finalLat, dv.direction_deg, SIM_HOURS) },
    time_steps,
  };
}

// ── Exported mock ──────────────────────────────────────────────────────────

export const incidentMock = {
  createPrediction: (req: PredictionRequest) =>
    delay(800, buildTimeSteps(predictionResult, req.last_coordinate)),

  getPrediction: (_id: string) =>
    delay(200, buildTimeSteps(predictionResult)),

  createBriefing: (_predictionId: string) =>
    delay(1200, briefingResult),
};
