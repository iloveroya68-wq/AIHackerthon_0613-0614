import type { RiskForecastResult, RiskGridCellProperties, GeoJSONFeatureCollection } from "@/types/contracts";

function delay<T>(ms: number, value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

// ── Sea area definitions ───────────────────────────────────────────────────

type BBox4 = [number, number, number, number];

interface AreaDef {
  bbox: BBox4;
  maxWind: number;
  maxWave: number;
  baseDri: number;
  peakOffsetH: number;
}

const SEA_AREAS: Record<string, AreaDef> = {
  "연평도 인근 서해":  { bbox: [124.1, 37.6, 124.9, 38.3], maxWind:  7.2, maxWave: 0.8, baseDri: 0.24, peakOffsetH: 3 },
  "인천/경기만":       { bbox: [124.5, 37.0, 126.0, 37.8], maxWind:  6.0, maxWave: 0.6, baseDri: 0.18, peakOffsetH: 4 },
  "목포/신안 해역":    { bbox: [125.2, 33.8, 126.2, 34.8], maxWind:  8.5, maxWave: 0.9, baseDri: 0.26, peakOffsetH: 3 },
  "군산/새만금":       { bbox: [125.0, 35.4, 126.3, 36.2], maxWind:  5.5, maxWave: 0.5, baseDri: 0.17, peakOffsetH: 5 },
  "통영/거제":         { bbox: [127.8, 34.5, 128.9, 34.95], maxWind:  6.8, maxWave: 0.7, baseDri: 0.21, peakOffsetH: 4 },
  "여수/거문도":       { bbox: [126.8, 33.5, 127.8, 34.5], maxWind:  7.0, maxWave: 0.8, baseDri: 0.20, peakOffsetH: 4 },
  "부산/영도":         { bbox: [128.9, 34.8, 129.6, 35.3], maxWind:  5.0, maxWave: 0.5, baseDri: 0.15, peakOffsetH: 5 },
  "포항/영일만":       { bbox: [129.5, 35.5, 131.0, 36.7], maxWind:  7.5, maxWave: 0.9, baseDri: 0.22, peakOffsetH: 4 },
  "속초/고성":         { bbox: [129.0, 37.8, 130.5, 38.9], maxWind:  8.8, maxWave: 1.0, baseDri: 0.28, peakOffsetH: 3 },
  "제주도 서방":       { bbox: [125.5, 32.5, 126.5, 33.5], maxWind:  9.0, maxWave: 1.1, baseDri: 0.27, peakOffsetH: 3 },
  "제주도 동방":       { bbox: [127.0, 32.5, 128.2, 33.5], maxWind:  8.0, maxWave: 0.9, baseDri: 0.23, peakOffsetH: 4 },
};

function simpleHash(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function buildRiskGrid(
  bbox: BBox4,
  areaName: string,
  baseDri: number,
): GeoJSONFeatureCollection<RiskGridCellProperties> {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const COLS = 14;
  const ROWS = 12;
  const dLon = (maxLon - minLon) / COLS;
  const dLat = (maxLat - minLat) / ROWS;

  const areaSeed = simpleHash(areaName);
  const hotspotCol = (areaSeed % 100) / 100;
  const hotspotRow = ((areaSeed >> 8) % 100) / 100;

  const features: GeoJSONFeatureCollection<RiskGridCellProperties>["features"] = [];

  for (let row = 0; row < ROWS; row++) {
    for (let col = 0; col < COLS; col++) {
      const nCol = (col + 0.5) / COLS;
      const nRow = (row + 0.5) / ROWS;
      const dist = Math.sqrt((nCol - hotspotCol) ** 2 + (nRow - hotspotRow) ** 2) / Math.SQRT2;
      const spatialFactor = 1 - dist * 0.75;

      const cellSeed = simpleHash(`${areaName}-${row}-${col}`);
      const noise = ((cellSeed % 1000) / 1000 - 0.5) * 0.18;

      const dri = Math.max(0.03, Math.min(0.55, baseDri * spatialFactor + noise));
      const risk_level = dri >= 0.65 ? "고위험" : dri >= 0.38 ? "주의" : "관찰";

      const lon0 = minLon + col * dLon;
      const lat0 = minLat + row * dLat;

      features.push({
        type: "Feature",
        properties: { risk_level, dri_score: parseFloat(dri.toFixed(3)) },
        geometry: {
          type: "Polygon",
          coordinates: [[
            [lon0, lat0],
            [lon0 + dLon, lat0],
            [lon0 + dLon, lat0 + dLat],
            [lon0, lat0 + dLat],
            [lon0, lat0],
          ]],
        },
      });
    }
  }

  return { type: "FeatureCollection", features };
}

function buildRiskForecast(areaName?: string, timeRangeStart?: string): RiskForecastResult {
  const name = areaName && areaName in SEA_AREAS ? areaName : "연평도 인근 서해";
  const def = SEA_AREAS[name];
  const now = new Date();
  const targetTime = timeRangeStart ? new Date(timeRangeStart) : now;
  const forecastH = Math.round((targetTime.getTime() - now.getTime()) / 3600_000);
  // 시간대별 DRI 변동: 6h 주기 sine 변동 ±20%
  const variation = Math.sin(forecastH * Math.PI / 36) * 0.20;
  const adjustedDri = Math.max(0.05, Math.min(0.97, def.baseDri + variation));
  const adjustedWind = Math.max(1, def.maxWind * (0.85 + (variation + 0.20) / 2));
  const adjustedWave = Math.max(0.1, def.maxWave * (0.85 + (variation + 0.20) / 2));
  const peakTime = new Date(targetTime.getTime() + def.peakOffsetH * 3600_000);
  const endTime = new Date(targetTime.getTime() + 3 * 3600_000);
  const tidalTime = new Date(targetTime.getTime() + (def.peakOffsetH + 0.5) * 3600_000);
  const highCount = simpleHash(`${name}-vessels`) % 20 + 5;
  const highArea = 0.0;

  const windSev: "고위험" | "주의" | "관찰" = adjustedWind >= 14 ? "고위험" : adjustedWind >= 10 ? "주의" : "관찰";
  const waveSev: "고위험" | "주의" | "관찰" = adjustedWave >= 2.0 ? "고위험" : adjustedWave >= 1.5 ? "주의" : "관찰";
  const tidalHH = String(peakTime.getHours()).padStart(2, "0");
  const tidalMM = String(peakTime.getMinutes()).padStart(2, "0");

  const w = parseFloat(adjustedWind.toFixed(1));
  const wv = parseFloat(adjustedWave.toFixed(1));

  const windDesc = w >= 14
    ? `${w} m/s — 소형어선 귀항 권고 수준, 출항 통제 검토`
    : w >= 10
    ? `${w} m/s — 조업 한계 근접, 낚시어선 출항 주의`
    : `${w} m/s — 정상 운항 가능 (소형어선 한계 10 m/s)`;

  const waveDesc = wv >= 2.0
    ? `유의파고 ${wv} m — 소형어선 안전기준(2 m) 초과, 전복 위험`
    : wv >= 1.5
    ? `유의파고 ${wv} m — 낚시어선 제한기준(1.5 m) 초과, 선체 동요 주의`
    : `유의파고 ${wv} m — 정상 수준 (낚시어선 기준 1.5 m 이하)`;

  // Action 1 — 가장 심각한 요인 기반
  const waveEst = parseFloat((0.0248 * w ** 2).toFixed(1));
  let act1: { priority: number; action: string; target: string };
  if (w >= 14) {
    act1 = { priority: 1, action: "소형어선 출항 통제 요청",
      target: `예측 풍속 ${w} m/s — 소형어선 운항한계(14 m/s) 초과, 관할 어항 출항 금지 공문 발송` };
  } else if (waveEst >= 2.0) {
    act1 = { priority: 1, action: "소형어선 운항 제한 발령",
      target: `추정 유의파고 ${waveEst} m — 소형어선 안전기준(2.0 m) 초과, 낚시어선 포함 즉시 귀항 권고` };
  } else if (w >= 10) {
    act1 = { priority: 1, action: "낚시어선 출항 자제 권고",
      target: `예측 풍속 ${w} m/s — 낚시어선 운항주의보 기준(10 m/s) 초과, 자발적 귀항 유도` };
  } else {
    act1 = { priority: 1, action: "기상 모니터링 강화",
      target: `예측 풍속 ${w} m/s — 3시간 간격 재분석, 임계치 도달 시 즉시 경보 전환` };
  }

  // Action 2 — peakTime 기반 타이밍
  const hoursToP = def.peakOffsetH;
  const peakHH = String(peakTime.getHours()).padStart(2, "0");
  const peakMM = String(peakTime.getMinutes()).padStart(2, "0");
  const peakStr = `${peakHH}:${peakMM}`;
  let act2: { priority: number; action: string; target: string };
  if (hoursToP > 3) {
    act2 = { priority: 2, action: "순찰정 사전 배치",
      target: `최고 위험 예상 ${peakStr} (${hoursToP}시간 후) — 피크 2시간 전까지 고위험 해역 진입 완료` };
  } else if (hoursToP > 1) {
    act2 = { priority: 2, action: "V-Pass 귀항 권고 즉시 발송",
      target: `최고 위험 ${peakStr}까지 약 ${hoursToP}시간 — 조업 중인 소형어선 귀항 유도 개시` };
  } else {
    act2 = { priority: 2, action: "순찰정 긴급 출동·현장 통제",
      target: `최고 위험 ${peakStr} 1시간 이내 임박 — 고위험 해역 봉쇄, 표류 선박 수색 준비` };
  }

  // Action 3 — DRI 수준별 통신 프로토콜
  const driPct = Math.round(adjustedDri * 100);
  const act3 = adjustedDri >= 0.60
    ? { priority: 3, action: "VHF Ch.16 긴급 경보 방송",
        target: `DRI ${driPct}점(고위험) — 해당 해역 전 선박 대상 출항 금지·항만 입항 안내 송출` }
    : adjustedDri >= 0.30
    ? { priority: 3, action: "해양경계방송 출항 자제 안내",
        target: `DRI ${driPct}점(주의) — 소형선 출항 자제 및 기상 악화 대비 안전 점검 권고` }
    : { priority: 3, action: "정기 위치 보고 독려",
        target: `DRI ${driPct}점(정상) — VHF Ch.16 2시간 간격 위치 보고 요청, 일출·일몰 전후 집중 순찰` };

  const actions = [act1, act2, act3];

  return {
    forecast_id: `mock-${simpleHash(name + forecastH).toString(16).slice(0, 8)}`,
    forecasted_at: now.toISOString(),
    area_name: name,
    bbox: def.bbox,
    time_range_start: targetTime.toISOString(),
    time_range_end: endTime.toISOString(),
    peak_risk_time: peakTime.toISOString(),
    vessel_types_targeted: ["소형어선", "레저보트"],
    risk_grid: buildRiskGrid(def.bbox, name, adjustedDri),
    dri_score: adjustedDri,
    dri_percentile: parseFloat((adjustedDri * 100).toFixed(1)),
    risk_causes: [
      { factor: "풍속",     description: windDesc, severity: windSev },
      { factor: "파고",     description: waveDesc, severity: waveSev },
      { factor: "조류 반전", description: `${tidalHH}:${tidalMM} 조류 반전 예정 — 표류체 방향 급변, 협수로 주의`, severity: adjustedDri >= 0.65 ? "고위험" : "주의" },
    ],
    recommended_actions: actions,
    max_wind_speed_ms: w,
    max_wave_height_m: wv,
    max_current_speed_kt: parseFloat((def.baseDri * 1.5 * (0.85 + (variation + 0.20) / 2)).toFixed(2)),
    tidal_reversal_time: tidalTime.toISOString(),
    vessels_at_risk_count: highCount,
    high_risk_area_km2: highArea,
  };
}

// ── Exported mock ──────────────────────────────────────────────────────────

export const riskMock = {
  getRiskForecast: (params?: { area_name?: string; time_range_start?: string }) =>
    delay(600, buildRiskForecast(params?.area_name, params?.time_range_start)),
  getRiskForecastBatch: () => {
    const batch: Record<string, RiskForecastResult> = {};
    Object.keys(SEA_AREAS).forEach((name) => { batch[name] = buildRiskForecast(name); });
    return delay(600, batch);
  },
};
