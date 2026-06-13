import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, GeoJSON, useMap } from "react-leaflet";
import { api } from "@/api";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import type { RiskLevel, RiskGridCellProperties, RiskForecastResult } from "@/types/contracts";
import { SEA_AREAS } from "@/api/risk/seaAreas";
import { loadKoreaGeoJSON, cellOverlapsLand } from "@/map/landMask";
import "leaflet/dist/leaflet.css";
import "./Tab3Risk.css";

const RISK_COLOR: Record<RiskLevel, string> = {
  고위험: "#ef4444",
  주의:   "#f59e0b",
  관찰:   "#22c55e",
};

const HEATMAP_STYLE: Record<RiskLevel, L.PathOptions> = {
  고위험: { color: "#ff2020", fillColor: "#ef4444", fillOpacity: 0.80, weight: 1.0, opacity: 1.0, className: "heatcell-high" },
  주의:   { color: "#fbbf24", fillColor: "#f59e0b", fillOpacity: 0.60, weight: 0.6, opacity: 0.9, className: "heatcell-caution" },
  관찰:   { color: "#4ade80", fillColor: "#22c55e", fillOpacity: 0.35, weight: 0.6, opacity: 0.7, className: "heatcell-watch" },
};

const RISK_LABEL: Record<RiskLevel, string> = {
  고위험: "고위험",
  주의:   "주의",
  관찰:   "정상",
};

type HotspotZone = "사고다발구역" | "주의구역";
interface HotspotProperties {
  accident_count: number;
  fatal_count:    number;
  zone:           HotspotZone;
  dominant_cause: string;
  dominant_type:  string;
}

import type { PathOptions } from "leaflet";

const AREA_NAMES = Object.keys(SEA_AREAS);
const ROTATION_MS = 5000;

// 울진/삼척 연안 모니터링 격자 (0.0333° × 0.0333° 셀, 24열 × 15행 — lat 36.80~37.30)
const ULJIN_GRID: GeoJSON.FeatureCollection = (() => {
  const CS = 0.10 / 3;
  const features: GeoJSON.Feature[] = [];
  for (let r = 0; r < 15; r++) {
    for (let c = 0; c < 24; c++) {
      const lon = Math.round((129.00 + c * CS) * 1000) / 1000;
      const lat = Math.round((36.80 + r * CS) * 1000) / 1000;
      features.push({
        type: "Feature",
        properties: {},
        geometry: {
          type: "Polygon",
          coordinates: [[
            [lon, lat], [lon + CS, lat],
            [lon + CS, lat + CS], [lon, lat + CS],
            [lon, lat],
          ]],
        },
      });
    }
  }
  return { type: "FeatureCollection", features };
})();
const OVERVIEW_CENTER: [number, number] = [36.0, 127.2];
const OVERVIEW_ZOOM = 6;

function RecenterView({ center, zoom }: { center: [number, number]; zoom: number }) {
  const map = useMap();
  useEffect(() => {
    map.setView(center, zoom, { animate: true });
  }, [center[0], center[1], zoom]);
  return null;
}

interface Tab3RiskProps {
  onRegisterEmergency?: (fn: () => void) => void;
}

export function Tab3Risk({ onRegisterEmergency }: Tab3RiskProps) {
  const [selectedArea, setSelectedArea] = useState<string | null>(null);
  const [riskForecast, setRiskForecast] = useState<RiskForecastResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [landReady, setLandReady] = useState(false);
  const [showHotspots, setShowHotspots] = useState(true);
  const [allHotspots, setAllHotspots] = useState<GeoJSON.FeatureCollection | null>(null);
  const [forecastHours, setForecastHours] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  // 'idle' → 'map'(4초 지도 표시) → 'alert'(경보 모달)
  const [emergencyPhase, setEmergencyPhase] = useState<'idle' | 'map' | 'alert'>('idle');
  const emergencyActiveRef = useRef(false);
  const forecastCacheRef = useRef<Map<string, RiskForecastResult>>(new Map());

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rotationIndexRef = useRef(-1);
  const rotationIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const selectedAreaRef = useRef<string | null>(null);
  useEffect(() => { selectedAreaRef.current = selectedArea; }, [selectedArea]);
  const loadingRef = useRef(false);
  useEffect(() => { loadingRef.current = loading; }, [loading]);

  useEffect(() => {
    loadKoreaGeoJSON().then(() => setLandReady(true)).catch(console.error);
  }, []);

  useEffect(() => {
    fetch("/accidentHotspots.json")
      .then((r) => r.json())
      .then((data: GeoJSON.FeatureCollection) => setAllHotspots(data))
      .catch(console.error);
  }, []);

  // 탭 진입 시 전체 해역 병렬 프리페치 → 이후 전환은 즉시 렌더
  // 배치 fetch → 캐시 갱신, 현재 해역 즉시 반영
  const refreshAllAreas = useCallback(() => {
    api.getRiskForecastBatch()
      .then((batch) => {
        Object.entries(batch).forEach(([name, result]) => {
          forecastCacheRef.current.set(name, result);
          if (name === selectedAreaRef.current) setRiskForecast(result);
        });
      })
      .catch(console.error);
  }, []);

  // 탭 진입 시 두 방식 성능 비교 후 배치 방식 채택, 이후 10분마다 갱신
  useEffect(() => {
    const runComparison = async () => {
      // 1) 병렬 개별 호출
      const t1 = performance.now();
      await Promise.all(AREA_NAMES.map((name) => api.getRiskForecast({ area_name: name }).catch(() => null)));
      const parallel_ms = Math.round(performance.now() - t1);

      // 2) 배치 단일 호출 (캐시 워밍 후)
      const t2 = performance.now();
      const batch = await api.getRiskForecastBatch().catch(() => null);
      const batch_ms = Math.round(performance.now() - t2);

      console.info(`[DRIFT] 해역 로드 비교 — 병렬 개별: ${parallel_ms}ms / 배치: ${batch_ms}ms → 배치 ${parallel_ms > batch_ms ? "빠름 ✓" : "느림"}`);

      if (batch) {
        Object.entries(batch).forEach(([name, result]) => {
          forecastCacheRef.current.set(name, result);
          if (name === selectedAreaRef.current) setRiskForecast(result);
        });
      }
    };

    runComparison();
    const interval = setInterval(refreshAllAreas, 10 * 60 * 1000);
    return () => clearInterval(interval);
  }, [refreshAllAreas]);

  // 해역 변경 시 캐시 우선 조회, 없으면 API 호출
  useEffect(() => {
    if (emergencyActiveRef.current) return; // 비상모드 중에는 fetch로 덮어쓰지 않음
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!selectedArea) {
      setRiskForecast(null);
      setError(null);
      setLoading(false);
      setForecastHours(0);
      return;
    }
    setForecastHours(0);
    setError(null);
    const cached = forecastCacheRef.current.get(selectedArea);
    if (cached) {
      setRiskForecast(cached);
      setLoading(false);
    } else {
      setRiskForecast(null);
      setLoading(true);
      api.getRiskForecast({ area_name: selectedArea })
        .then((result) => {
          forecastCacheRef.current.set(selectedArea, result);
          setRiskForecast(result);
        })
        .catch((e) => setError(e?.message ?? "서버 연결 실패"))
        .finally(() => setLoading(false));
    }
  }, [selectedArea]);

  // 자동 순환 재생/정지
  useEffect(() => {
    if (rotationIntervalRef.current) {
      clearInterval(rotationIntervalRef.current);
      rotationIntervalRef.current = null;
    }
    if (!isPlaying) return;

    const current = selectedAreaRef.current;
    if (current) {
      // 이미 특정 해역이 선택된 상태면 거기서 바로 이어서 순환
      rotationIndexRef.current = AREA_NAMES.indexOf(current);
      rotationIntervalRef.current = setInterval(() => {
        if (loadingRef.current) return;
        rotationIndexRef.current = (rotationIndexRef.current + 1) % AREA_NAMES.length;
        setSelectedArea(AREA_NAMES[rotationIndexRef.current]);
      }, ROTATION_MS);
    } else {
      // 전체 해역(overview)을 4초 보여준 뒤 첫 번째 해역부터 순환 시작
      rotationIndexRef.current = -1;
      const startTimer = setTimeout(() => {
        rotationIndexRef.current = 0;
        setSelectedArea(AREA_NAMES[0]);
        rotationIntervalRef.current = setInterval(() => {
          if (loadingRef.current) return;
          rotationIndexRef.current = (rotationIndexRef.current + 1) % AREA_NAMES.length;
          setSelectedArea(AREA_NAMES[rotationIndexRef.current]);
        }, ROTATION_MS);
      }, ROTATION_MS);
      return () => {
        clearTimeout(startTimer);
        if (rotationIntervalRef.current) clearInterval(rotationIntervalRef.current);
      };
    }

    return () => {
      if (rotationIntervalRef.current) clearInterval(rotationIntervalRef.current);
    };
  }, [isPlaying]);

  // 시연용 비상모드 핸들러
  const handleEmergency = useCallback(() => {
    const TARGET = "목포/신안 해역";
    const TARGET_BBOX: [number, number, number, number] = [125.2, 33.8, 126.2, 34.8];

    emergencyActiveRef.current = true;
    setIsPlaying(false);
    setSelectedArea(TARGET);
    rotationIndexRef.current = AREA_NAMES.indexOf(TARGET);

    // 캐시 없이도 즉시 고위험 격자 구성
    const now = new Date();
    const peakTime = new Date(now.getTime() + 40 * 60_000);
    const [minLon, minLat, maxLon, maxLat] = TARGET_BBOX;
    const COLS = 14, ROWS = 12;
    const dLon = (maxLon - minLon) / COLS;
    const dLat = (maxLat - minLat) / ROWS;
    const gridFeatures = [];
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const lon0 = minLon + c * dLon;
        const lat0 = minLat + r * dLat;
        gridFeatures.push({
          type: "Feature" as const,
          properties: { risk_level: "고위험" as const, dri_score: 0.91 },
          geometry: {
            type: "Polygon" as const,
            coordinates: [[
              [lon0, lat0], [lon0 + dLon, lat0],
              [lon0 + dLon, lat0 + dLat], [lon0, lat0 + dLat],
              [lon0, lat0],
            ]],
          },
        });
      }
    }

    setRiskForecast({
      forecasted_at: now.toISOString(),
      area_name: TARGET,
      bbox: TARGET_BBOX,
      time_range_start: now.toISOString(),
      time_range_end: new Date(now.getTime() + 3 * 3600_000).toISOString(),
      peak_risk_time: peakTime.toISOString(),
      vessel_types_targeted: ["소형어선", "레저보트"],
      risk_grid: { type: "FeatureCollection", features: gridFeatures },
      dri_score: 0.91,
      dri_percentile: 91.0,
      max_wind_speed_ms: 18.5,
      max_wave_height_m: 2.8,
      max_current_speed_kt: 3.2,
      tidal_reversal_time: new Date(peakTime.getTime() + 15 * 60_000).toISOString(),
      vessels_at_risk_count: 147,
      high_risk_area_km2: 42.3,
      risk_causes: [
        { factor: "풍속", description: "18.5 m/s — 소형어선 운항한계(14 m/s) 초과, 출항 통제 수준", severity: "고위험" },
        { factor: "파고", description: "유의파고 2.8 m — 소형어선 안전기준(2 m) 초과, 전복 위험", severity: "고위험" },
        { factor: "조류 반전", description: `${peakTime.getHours()}:${String(peakTime.getMinutes()).padStart(2,"0")} 조류 반전 예정 — 표류체 방향 급변, 협수로 주의`, severity: "주의" },
      ],
      recommended_actions: [
        { priority: 1, action: "소형어선 즉시 출항 통제", target: "목포·신안 관할 어항 전체 출항 금지 공문 발송" },
        { priority: 2, action: "조업 중 선박 긴급 귀항 권고", target: "V-Pass 전 선박 긴급 귀항 유도 문자 발송" },
        { priority: 3, action: "VHF Ch.16 긴급 경보 방송", target: "해당 해역 전 선박 대상 기상 경보 송출" },
      ],
    });

    // 4초 후 경보 모달로 전환
    setEmergencyPhase('map');
    setTimeout(() => setEmergencyPhase('alert'), 4000);
  }, []);

  useEffect(() => {
    onRegisterEmergency?.(handleEmergency);
  }, [handleEmergency, onRegisterEmergency]);

  const handleSliderChange = useCallback((hours: number) => {
    if (!selectedArea) return;
    setForecastHours(hours);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setRiskForecast(null);
      setError(null);
      setLoading(true);
      const timeStr = hours > 0
        ? new Date(Date.now() + hours * 3600_000).toISOString()
        : undefined;
      api.getRiskForecast({ area_name: selectedArea, time_range_start: timeStr })
        .then(setRiskForecast)
        .catch((e) => setError(e?.message ?? "서버 연결 실패"))
        .finally(() => setLoading(false));
    }, 400);
  }, [selectedArea]);

  const handleAreaSelect = useCallback((name: string) => {
    if (selectedArea === name) {
      // 같은 해역 재클릭 → 전체 보기로 복귀
      setSelectedArea(null);
      setIsPlaying(false);
    } else {
      rotationIndexRef.current = AREA_NAMES.indexOf(name);
      setSelectedArea(name);
    }
  }, [selectedArea]);

  const targetTime = useMemo(
    () => new Date(Date.now() + forecastHours * 3600_000),
    [forecastHours],
  );

  const isOverview = selectedArea === null;
  const bbox = selectedArea
    ? (SEA_AREAS[selectedArea]?.bbox ?? [126.0, 34.0, 127.0, 35.0])
    : [126.0, 34.0, 127.0, 35.0];
  const mapCenter: [number, number] = isOverview
    ? OVERVIEW_CENTER
    : [(bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2];
  const mapZoom = isOverview ? OVERVIEW_ZOOM : 9;

  const filteredForecast = useMemo<RiskForecastResult | null>(() => {
    if (!riskForecast) return null;
    if (!landReady) return riskForecast;
    const seaFeatures = riskForecast.risk_grid.features.filter((f) => {
      const coords = (f.geometry as GeoJSON.Polygon).coordinates[0];
      return !cellOverlapsLand(coords);
    });
    return { ...riskForecast, risk_grid: { ...riskForecast.risk_grid, features: seaFeatures } };
  }, [riskForecast, landReady]);

  const seaHotspots = useMemo<GeoJSON.FeatureCollection | null>(() => {
    if (!allHotspots) return null;
    if (!landReady) return allHotspots;
    const features = allHotspots.features.filter((f) => {
      const coords = (f.geometry as GeoJSON.Polygon).coordinates[0];
      return !cellOverlapsLand(coords);
    });
    return { ...allHotspots, features };
  }, [allHotspots, landReady]);

  const areaHotspots = useMemo<GeoJSON.FeatureCollection | null>(() => {
    if (!seaHotspots || !selectedArea) return null;
    const areaBbox = SEA_AREAS[selectedArea]?.bbox ?? [126.0, 34.0, 127.0, 35.0];
    const [minLon, minLat, maxLon, maxLat] = areaBbox;
    const features = seaHotspots.features.filter((f) => {
      const coords = (f.geometry as GeoJSON.Polygon).coordinates[0];
      const cx = (coords[0][0] + coords[2][0]) / 2;
      const cy = (coords[0][1] + coords[2][1]) / 2;
      return cx >= minLon && cx <= maxLon && cy >= minLat && cy <= maxLat;
    });
    return { type: "FeatureCollection", features };
  }, [seaHotspots, selectedArea]);

  const maxAccidentCount = useMemo(() => {
    if (!areaHotspots || areaHotspots.features.length === 0) return 1;
    return Math.max(...areaHotspots.features.map((f) => (f.properties as HotspotProperties).accident_count));
  }, [areaHotspots]);

  const totalAccidentCount = useMemo(() => {
    if (!seaHotspots) return null;
    return seaHotspots.features.reduce(
      (sum, f) => sum + ((f.properties as HotspotProperties).accident_count ?? 0), 0,
    );
  }, [seaHotspots]);

  const filteredUljinGrid = useMemo<GeoJSON.FeatureCollection>(() => {
    if (!landReady) return ULJIN_GRID;
    const features = ULJIN_GRID.features.filter((f) => {
      const coords = (f.geometry as GeoJSON.Polygon).coordinates[0];
      return !cellOverlapsLand(coords);
    });
    return { ...ULJIN_GRID, features };
  }, [landReady]);

  const areaBufferCells = useMemo<GeoJSON.FeatureCollection | null>(() => {
    if (!areaHotspots || areaHotspots.features.length === 0) return null;
    const CS = 0.05;
    const round5 = (v: number) => Math.round(v * 100000) / 100000;

    const hotspotKeys = new Set<string>();
    for (const f of areaHotspots.features) {
      const c = (f.geometry as GeoJSON.Polygon).coordinates[0];
      hotspotKeys.add(`${c[0][0]},${c[0][1]}`);
    }

    const bufferKeys = new Set<string>();
    const features: GeoJSON.Feature[] = [];

    for (const f of areaHotspots.features) {
      const c = (f.geometry as GeoJSON.Polygon).coordinates[0];
      const lon0 = c[0][0];
      const lat0 = c[0][1];
      for (let dr = -1; dr <= 1; dr++) {
        for (let dc = -1; dc <= 1; dc++) {
          if (dr === 0 && dc === 0) continue;
          const nLon0 = round5(lon0 + dc * CS);
          const nLat0 = round5(lat0 + dr * CS);
          const key = `${nLon0},${nLat0}`;
          if (hotspotKeys.has(key) || bufferKeys.has(key)) continue;
          bufferKeys.add(key);
          const nLon1 = round5(nLon0 + CS);
          const nLat1 = round5(nLat0 + CS);
          const cellCoords: GeoJSON.Position[] = [
            [nLon0, nLat0], [nLon1, nLat0],
            [nLon1, nLat1], [nLon0, nLat1],
            [nLon0, nLat0],
          ];
          if (landReady && cellOverlapsLand(cellCoords)) continue;
          features.push({
            type: "Feature",
            properties: {},
            geometry: { type: "Polygon", coordinates: [cellCoords] },
          });
        }
      }
    }
    return { type: "FeatureCollection", features };
  }, [areaHotspots, landReady]);

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <div className="flex flex-1 overflow-hidden">

        {/* ── 좌측 패널 ──────────────────────────────────────────────────── */}
        <aside className="w-64 shrink-0 bg-gradient-to-b from-navy-900 to-navy-950 border-r border-navy-700/70 flex flex-col overflow-y-auto">
          <div className="p-4 border-b border-navy-700/60">

            {/* 해역 선택 헤더 + 재생/일시정지 버튼 */}
            <div className="flex items-center gap-2 mb-3">
              <span className="w-1 h-4 rounded-full bg-cyan-400 shadow-[0_0_6px_rgba(0,212,255,0.7)]" />
              <h2 className="text-xs font-semibold text-cyan-400 uppercase tracking-wider">
                해역 선택
              </h2>
              <button
                onClick={() => setIsPlaying((v) => !v)}
                title={isPlaying ? "일시정지" : "자동 순환 시작"}
                className="ml-auto w-6 h-6 flex items-center justify-center rounded text-cyan-400 hover:bg-cyan-400/15 transition-colors"
              >
                {isPlaying ? (
                  <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
                    <rect x="3" y="2" width="3.5" height="12" rx="1" />
                    <rect x="9.5" y="2" width="3.5" height="12" rx="1" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
                    <path d="M4 2.5l9 5.5-9 5.5V2.5z" />
                  </svg>
                )}
              </button>
            </div>

            {/* 자동 순환 중 표시 */}
            {isPlaying && (
              <div className="flex items-center gap-1.5 mb-2">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                <span className="text-[10px] text-cyan-400/70">자동 순환 중 · 5초마다 전환</span>
              </div>
            )}

            {/* 전체 해역 보기 버튼 (상세 보기 모드일 때만) */}
            {selectedArea && (
              <button
                onClick={() => { setSelectedArea(null); setIsPlaying(false); }}
                className="w-full text-left text-xs px-3 py-2 rounded mb-2 transition-all bg-navy-700/50 text-slate-400 hover:bg-navy-700 hover:text-slate-300 border border-navy-600/50"
              >
                ← 전체 해역 보기
              </button>
            )}

            <div className="flex flex-col gap-1">
              {AREA_NAMES.map((name) => (
                <button
                  key={name}
                  onClick={() => handleAreaSelect(name)}
                  className={[
                    "text-left text-xs px-3 py-2 rounded transition-all",
                    selectedArea === name
                      ? "bg-cyan-400/15 text-cyan-300 border border-cyan-400/30"
                      : "text-slate-400 hover:bg-navy-800 hover:text-slate-300 border border-transparent",
                  ].join(" ")}
                >
                  {name}
                </button>
              ))}
            </div>
          </div>

          {/* DRI 게이지 + 통계 (상세 보기, 데이터 있을 때) */}
          {riskForecast && !loading && (
            <div className="p-4 flex flex-col gap-4">
              <div className="bg-navy-800/60 border border-navy-600/50 rounded-xl p-4 text-center shadow-inner">
                <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2">Drift Risk Index</p>
                <DriGauge score={riskForecast.dri_score} peakTime={riskForecast.peak_risk_time} />
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {[
                  { label: "최대 풍속", value: `${riskForecast.max_wind_speed_ms} m/s` },
                  { label: "최대 파고", value: `${riskForecast.max_wave_height_m} m` },
                  { label: "조류 속도", value: `${riskForecast.max_current_speed_kt} kt` },
                  { label: "고위험 면적", value: `${riskForecast.high_risk_area_km2} km²` },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-navy-800/50 border border-navy-700/60 rounded-lg p-2.5 transition-colors hover:bg-navy-700/40">
                    <p className="text-slate-500 text-[10px] uppercase tracking-wide mb-0.5">{label}</p>
                    <p className="text-cyan-300 font-mono font-semibold">{value}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {loading && (
            <div className="flex-1 flex items-center justify-center py-8">
              <svg className="animate-spin h-6 w-6 text-cyan-400" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            </div>
          )}

          {/* 전체 보기 모드 안내 */}
          {isOverview && !loading && (
            <div className="p-4 text-center">
              <p className="text-[11px] text-slate-500 leading-relaxed">
                해역을 선택하면<br />상세 위험 정보를 확인할 수 있습니다
              </p>
              {totalAccidentCount !== null && (
                <p className="text-[10px] text-slate-600 mt-2">
                  전국 {totalAccidentCount.toLocaleString()}건 기반
                </p>
              )}
            </div>
          )}
        </aside>

        {/* ── 지도 영역 ────────────────────────────────────────────────── */}
        <div className="flex-1 relative overflow-hidden">
          <MapContainer
            center={OVERVIEW_CENTER}
            zoom={OVERVIEW_ZOOM}
            style={{ height: "100%", width: "100%" }}
            zoomControl
          >
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
            />
            <RecenterView center={mapCenter} zoom={mapZoom} />

            {/* 전체 해역 보기: 울진/삼척 모니터링 구역 */}
            {isOverview && (
              <GeoJSON
                key={`overview-uljin-zone-${landReady}`}
                data={filteredUljinGrid as unknown as GeoJSON.FeatureCollection}
                style={() => ({
                  fillColor: "#22c55e",
                  fillOpacity: 0.12,
                  color: "#34d399",
                  weight: 1.5,
                  opacity: 0.6,
                  dashArray: "6,5",
                  className: "heatcell-watch",
                } as PathOptions)}
                onEachFeature={(_feature, layer) => {
                  layer.bindTooltip("울진/삼척 해역<br/>동해 중부 모니터링 구역", { className: "risk-tooltip", sticky: true });
                }}
              />
            )}

            {/* 전체 해역 보기: 모든 사고다발구역 표시 */}
            {isOverview && seaHotspots && (
              <GeoJSON
                key="overview-all-hotspots"
                data={seaHotspots as unknown as GeoJSON.FeatureCollection}
                style={(feature) => {
                  const p = (feature?.properties ?? {}) as HotspotProperties;
                  const fillColor = p.zone === "사고다발구역" ? "#22c55e" : "#4ade80";
                  const borderColor = p.zone === "사고다발구역" ? "#22d3ee" : "#34d399";
                  return {
                    fillColor,
                    fillOpacity: p.zone === "사고다발구역" ? 0.45 : 0.25,
                    color: borderColor,
                    weight: p.zone === "사고다발구역" ? 2.0 : 1.5,
                    opacity: 0.9,
                    dashArray: p.zone === "주의구역" ? "6,4" : undefined,
                    className: "heatcell-watch",
                  } as PathOptions;
                }}
                onEachFeature={(feature, layer) => {
                  const p = feature.properties as HotspotProperties;
                  layer.bindTooltip(
                    `<b>${p.zone}</b><br/>2011–2023년 ${p.accident_count}건`,
                    { className: "risk-tooltip", sticky: true },
                  );
                }}
              />
            )}

            {/* 상세 보기: 버퍼 셀 */}
            {!isOverview && areaBufferCells && areaBufferCells.features.length > 0 && riskForecast && (
              <GeoJSON
                key={`dri-buffer-${selectedArea}-${riskForecast.forecasted_at}`}
                data={areaBufferCells as unknown as GeoJSON.FeatureCollection}
                style={() => {
                  const dri = riskForecast.dri_score;
                  const color = dri >= 0.60 ? "#ef4444" : dri >= 0.30 ? "#f59e0b" : "#22c55e";
                  return { fillColor: color, fillOpacity: 0.14, color, weight: 0.3, opacity: 0.35 } as PathOptions;
                }}
              />
            )}

            {/* 상세 보기: DRI 히트맵 */}
            {!isOverview && areaHotspots && areaHotspots.features.length > 0 && riskForecast && (
              <GeoJSON
                key={`dri-hotspot-${selectedArea}-${riskForecast.forecasted_at}-${showHotspots}`}
                data={areaHotspots as unknown as GeoJSON.FeatureCollection}
                style={(feature) => {
                  const p = (feature?.properties ?? {}) as HotspotProperties;
                  const dri = riskForecast.dri_score;
                  const color = dri >= 0.60 ? "#ef4444" : dri >= 0.30 ? "#f59e0b" : "#22c55e";
                  const intensity = Math.min(1, p.accident_count / maxAccidentCount);
                  const fillOpacity = p.zone === "사고다발구역"
                    ? 0.38 + intensity * 0.30
                    : 0.22 + intensity * 0.18;
                  const outlineColor = showHotspots
                    ? (p.zone === "사고다발구역" ? "#c084fc" : "#a78bfa")
                    : color;
                  const outlineWeight = showHotspots ? (p.zone === "사고다발구역" ? 2.5 : 1.5) : 0.5;
                  const dashArray = showHotspots && p.zone === "주의구역" ? "6,4" : undefined;
                  const cellClass = dri >= 0.60 ? "heatcell-high" : dri >= 0.30 ? "heatcell-caution" : "heatcell-watch";
                  return { fillColor: color, fillOpacity, color: outlineColor, weight: outlineWeight, opacity: 1.0, dashArray, className: cellClass } as PathOptions;
                }}
                onEachFeature={(feature, layer) => {
                  const p = feature.properties as HotspotProperties;
                  const dri = riskForecast.dri_score;
                  const driPct = Math.round(dri * 100);
                  const lvl = dri >= 0.60 ? "고위험" : dri >= 0.30 ? "주의" : "관찰";
                  const fatalInfo = p.fatal_count > 0 ? ` · 사망·실종 ${p.fatal_count}명` : "";
                  layer.bindTooltip(
                    `<b>${p.zone}</b> — DRI ${driPct} (${lvl})<br/>2011–2023년 ${p.accident_count}건${fatalInfo}<br/>주요 원인: ${p.dominant_cause}<br/>주요 유형: ${p.dominant_type}`,
                    { className: "risk-tooltip", sticky: true },
                  );
                }}
              />
            )}

            {/* 사고 이력 없는 해역: 격자 폴백 */}
            {!isOverview && filteredForecast && (!areaHotspots || areaHotspots.features.length === 0) && (
              <GeoJSON
                key={filteredForecast.area_name + filteredForecast.forecasted_at}
                data={filteredForecast.risk_grid as unknown as GeoJSON.FeatureCollection}
                style={(feature) => {
                  const p = feature?.properties as RiskGridCellProperties;
                  const lvl = p.risk_level as RiskLevel;
                  const dri = (p.dri_score ?? 0.2) as number;
                  const base = HEATMAP_STYLE[lvl] ?? HEATMAP_STYLE["관찰"];
                  const fillOpacity = lvl === "고위험" ? Math.min(0.95, 0.55 + dri * 0.45)
                                    : lvl === "주의"   ? Math.min(0.75, 0.28 + dri * 0.70)
                                    : Math.min(0.45, 0.20 + dri * 0.80);
                  return { ...base, fillOpacity } as PathOptions;
                }}
                onEachFeature={(feature, layer) => {
                  const p = feature.properties as RiskGridCellProperties;
                  layer.bindTooltip(
                    `<b>${p.risk_level}</b><br/>DRI ${(p.dri_score * 100).toFixed(0)}`,
                    { className: "risk-tooltip", sticky: true },
                  );
                }}
              />
            )}
          </MapContainer>

          {/* 타임라인 슬라이더 (상세 보기일 때만) */}
          {!isOverview && (
            <div className="absolute bottom-6 left-3 z-[1000] flex flex-col gap-2 w-72">
              <div className="bg-navy-900/90 border border-navy-700 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-cyan-400">예측 시점</p>
                  <span className="text-xs text-slate-300">
                    {forecastHours === 0 ? "현재" : `+${forecastHours}h`}
                    {" · "}
                    {targetTime.toLocaleString("ko-KR", {
                      month: "numeric", day: "numeric",
                      hour: "2-digit", minute: "2-digit",
                    })}
                  </span>
                </div>
                <input
                  type="range"
                  min={0} max={72} step={6}
                  value={forecastHours}
                  onChange={(e) => handleSliderChange(Number(e.target.value))}
                  className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-cyan-400"
                  style={{ background: `linear-gradient(to right, #22d3ee ${(forecastHours / 72) * 100}%, #1e293b ${(forecastHours / 72) * 100}%)` }}
                />
                <div className="flex justify-between text-[10px] text-slate-500 mt-1.5 select-none">
                  <span>지금</span>
                  <span>+1일</span>
                  <span>+2일</span>
                  <span>+3일</span>
                </div>
              </div>
            </div>
          )}

          {/* 전체 해역 보기 안내 (좌하단) */}
          {isOverview && totalAccidentCount !== null && (
            <div className="absolute bottom-6 left-3 z-[1000]">
              <div className="bg-navy-900/90 border border-navy-700 rounded-lg px-4 py-3">
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  전국 해상사고 다발구역 — {totalAccidentCount.toLocaleString()}건 기반<br />
                  <span className="text-slate-500">2011–2023 · 좌측 해역 선택 시 상세 분석</span>
                </p>
              </div>
            </div>
          )}

          {/* 로딩 오버레이 */}
          {loading && (
            <div className="absolute inset-0 bg-navy-900/60 flex items-center justify-center z-[1000]">
              <div className="flex items-center gap-3 bg-navy-900 border border-navy-700 rounded-lg px-5 py-3">
                <svg className="animate-spin h-5 w-5 text-cyan-400" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span className="text-sm text-slate-300">해역 데이터 로딩 중…</span>
              </div>
            </div>
          )}

          {/* 오류 오버레이 */}
          {error && !loading && selectedArea && (
            <div className="absolute inset-0 bg-navy-900/70 flex items-center justify-center z-[1000]">
              <div className="bg-navy-900 border border-red-500/40 rounded-lg px-6 py-4 text-center max-w-xs">
                <p className="text-red-400 font-semibold mb-1">서버 연결 오류</p>
                <p className="text-slate-400 text-xs">{error}</p>
                <button
                  onClick={() => {
                    setError(null);
                    setLoading(true);
                    api.getRiskForecast({ area_name: selectedArea })
                      .then(setRiskForecast)
                      .catch((e) => setError(e?.message ?? "서버 연결 실패"))
                      .finally(() => setLoading(false));
                  }}
                  className="mt-3 text-xs px-3 py-1.5 bg-cyan-400/15 text-cyan-300 border border-cyan-400/30 rounded hover:bg-cyan-400/25 transition"
                >
                  재시도
                </button>
              </div>
            </div>
          )}

          {/* 우하단: 범례 + 위험 요인 (상세 보기) */}
          {!isOverview && (
            <div className="absolute bottom-3 right-3 z-[1000] flex flex-col gap-2 w-64">
              <div className="bg-navy-900/90 border border-navy-700 rounded-lg p-3 text-xs flex gap-0">
                <div className="flex flex-col gap-1.5 pr-3 flex-1">
                  <button
                    onClick={() => setShowHotspots((v) => !v)}
                    className="flex items-center gap-1.5 hover:opacity-80 transition-opacity"
                  >
                    <span className="text-slate-400 font-medium whitespace-nowrap">과거 사고 이력</span>
                    <span className={[
                      "ml-auto text-[10px] px-1.5 py-0.5 rounded font-semibold",
                      showHotspots
                        ? "bg-violet-500/20 text-violet-300 border border-violet-500/30"
                        : "bg-navy-600 text-slate-500 border border-navy-500",
                    ].join(" ")}>
                      {showHotspots ? "ON" : "OFF"}
                    </span>
                  </button>
                  <div className="flex items-center gap-2">
                    <span className="w-4 h-3 rounded-sm shrink-0"
                      style={{ border: "2.5px solid #a855f7", background: "transparent" }} />
                    <span className={showHotspots ? "text-slate-400" : "text-slate-600"}>사고다발구역</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-4 h-3 rounded-sm shrink-0"
                      style={{ border: "2px dashed #c084fc", background: "transparent" }} />
                    <span className={showHotspots ? "text-slate-400" : "text-slate-600"}>주의구역</span>
                  </div>
                  {areaHotspots && showHotspots && (
                    <p className="text-[10px] text-slate-600">
                      {areaHotspots.features.filter(f => (f.properties as HotspotProperties).zone === "사고다발구역").length}개 다발 ·{" "}
                      {areaHotspots.features.filter(f => (f.properties as HotspotProperties).zone === "주의구역").length}개 주의
                    </p>
                  )}
                </div>
                <div className="w-px bg-navy-700 self-stretch mx-0.5" />
                <div className="flex flex-col gap-1.5 pl-3">
                  <p className="text-slate-400 font-medium">해양경보 등급</p>
                  {(["고위험", "주의", "관찰"] as RiskLevel[]).map((lvl) => (
                    <div key={lvl} className="flex items-center gap-2">
                      <span className="w-4 h-3 rounded-sm border shrink-0"
                        style={{
                          background: HEATMAP_STYLE[lvl].fillColor as string,
                          borderColor: HEATMAP_STYLE[lvl].color as string,
                        }} />
                      <span className="text-slate-300">{RISK_LABEL[lvl]}</span>
                    </div>
                  ))}
                  {areaHotspots && areaHotspots.features.length > 0 ? (
                    <p className="text-[10px] text-slate-500">채도 = 사고 빈도</p>
                  ) : filteredForecast ? (
                    <div className="mt-1 space-y-0.5">
                      <GridCounts forecast={filteredForecast} />
                    </div>
                  ) : null}
                </div>
              </div>

              {riskForecast && !loading && (
                <div className="bg-navy-900/90 border border-navy-700 rounded-lg p-3 text-xs">
                  <p className="text-white font-medium mb-2">위험 요인</p>
                  {riskForecast.risk_causes.map((cause, i) => (
                    <div key={i} className="flex items-start gap-2 mb-1.5">
                      <span className="mt-1 w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ background: RISK_COLOR[cause.severity] }} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1">
                          <span className="text-white font-medium">{cause.factor}</span>
                          <span className="ml-auto shrink-0 text-[10px] px-1 py-px rounded"
                            style={{ color: RISK_COLOR[cause.severity], background: `${RISK_COLOR[cause.severity]}20` }}>
                            {RISK_LABEL[cause.severity]}
                          </span>
                        </div>
                        <p className="text-[10px] text-slate-300 leading-snug mt-px">{cause.description}</p>
                      </div>
                    </div>
                  ))}
                  {riskForecast.tidal_reversal_time && (
                    <div className="flex items-start gap-2 mb-1.5">
                      <span className="mt-1 w-1.5 h-1.5 rounded-full shrink-0 bg-amber-400" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1">
                          <span className="text-white font-medium">조류 반전</span>
                          <span className="ml-auto shrink-0 text-[10px] px-1 py-px rounded text-amber-400 bg-amber-400/15">주의</span>
                        </div>
                        <p className="text-[10px] text-slate-300 leading-snug mt-px">
                          예상 {new Date(riskForecast.tidal_reversal_time).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })} — 협수로 통항 주의
                        </p>
                      </div>
                    </div>
                  )}
                  <div className="mt-2 pt-2 border-t border-navy-700">
                    <p className="text-white font-medium mb-2">권고 조치</p>
                    {riskForecast.recommended_actions.map((action) => (
                      <div key={action.priority} className="flex items-start gap-2 mb-1.5">
                        <span className={[
                          "shrink-0 w-4 h-4 rounded-full text-[9px] font-bold flex items-center justify-center mt-0.5",
                          action.priority === 1 ? "bg-red-500 text-white"
                            : action.priority === 2 ? "bg-amber-500 text-white"
                            : "bg-navy-600 text-slate-200",
                        ].join(" ")}>{action.priority}</span>
                        <div>
                          <p className="text-white">{action.action}</p>
                          <p className="text-[10px] text-slate-300 mt-px">{action.target}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 우하단: 전체 보기 범례 */}
          {isOverview && (
            <div className="absolute bottom-3 right-3 z-[1000] w-48">
              <div className="bg-navy-900/90 border border-navy-700 rounded-lg p-3 text-xs">
                <p className="text-slate-400 font-medium mb-2">사고 구역 유형</p>
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-2">
                    <span className="w-4 h-3 rounded-sm shrink-0"
                      style={{ border: "2px solid #22d3ee", background: "rgba(34,197,94,0.45)" }} />
                    <span className="text-slate-400">사고다발구역</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-4 h-3 rounded-sm shrink-0"
                      style={{ border: "2px dashed #34d399", background: "rgba(74,222,128,0.25)" }} />
                    <span className="text-slate-400">주의구역</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
      <DisclaimerBanner />

      {/* ── 비상모드: 지도 강조 (4초) ─────────────────────────────────── */}
      {emergencyPhase === 'map' && (
        <div className="fixed inset-0 z-[9998] pointer-events-none">
          {/* 맥동 빨간 테두리 */}
          <div className="absolute inset-0 border-4 border-red-500 animate-pulse rounded-none" />
          {/* 상단 상황 배너 */}
          <div className="absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-3 bg-red-600/90 backdrop-blur-sm border border-red-400/60 rounded-xl px-6 py-3 shadow-[0_0_30px_rgba(239,68,68,0.6)]">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-300 opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-red-200" />
            </span>
            <span className="text-white font-bold text-sm tracking-wide">목포/신안 해역 — 고위험 감지</span>
          </div>
        </div>
      )}

      {/* ── 비상모드: 경보 상세 모달 ──────────────────────────────────── */}
      {emergencyPhase === 'alert' && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/75 backdrop-blur-sm">
          <div className="relative w-full max-w-lg mx-4 bg-navy-900 border-2 border-red-500/70 rounded-2xl shadow-[0_0_40px_rgba(239,68,68,0.5)] overflow-hidden">

            {/* 헤더 */}
            <div className="bg-red-500/15 border-b border-red-500/30 px-6 py-4 flex items-center gap-3">
              <span className="relative flex h-4 w-4">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-4 w-4 bg-red-500" />
              </span>
              <div>
                <p className="text-red-400 font-bold text-base tracking-wide">목포/신안 해역 긴급 경보</p>
                <p className="text-red-400/60 text-[11px]">
                  {new Date().toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" })} 자동 감지
                </p>
              </div>
              <span className="ml-auto text-[10px] px-2 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30 font-bold tracking-widest">
                EMERGENCY
              </span>
            </div>

            {/* 본문 — 문제 원인 */}
            <div className="px-6 py-5 flex flex-col gap-4">

              {/* 위험 요인 */}
              <div className="flex flex-col gap-2">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">감지된 위험 요인</p>
                {[
                  { label: "풍속 18.5 m/s", desc: "소형어선 운항한계(14 m/s) 초과 — 즉시 출항 통제 필요", level: "고위험" },
                  { label: "유의파고 2.8 m", desc: "안전기준(2 m) 초과 — 소형어선 전복 위험 수준", level: "고위험" },
                  { label: "조류 반전 임박", desc: "40분 내 조류 반전 예정 — 표류 방향 급변, 협수로 주의", level: "주의" },
                ].map((r) => (
                  <div key={r.label} className="flex items-start gap-3 bg-navy-800/60 border border-navy-700 rounded-lg px-3 py-2.5">
                    <span className={[
                      "shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded mt-0.5",
                      r.level === "고위험" ? "bg-red-500/20 text-red-400 border border-red-500/30" : "bg-amber-500/20 text-amber-400 border border-amber-500/30",
                    ].join(" ")}>{r.level}</span>
                    <div>
                      <p className="text-xs font-semibold text-white">{r.label}</p>
                      <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">{r.desc}</p>
                    </div>
                  </div>
                ))}
              </div>

              {/* 권고 조치 */}
              <div className="bg-amber-500/8 border border-amber-500/25 rounded-xl px-4 py-3">
                <p className="text-xs font-semibold text-amber-400 mb-2">즉각 조치 사항</p>
                <ul className="flex flex-col gap-1.5 text-[11px] text-slate-300">
                  <li className="flex items-start gap-2"><span className="text-red-400 font-bold shrink-0">①</span>목포·신안 관할 어항 전체 출항 금지 공문 발송</li>
                  <li className="flex items-start gap-2"><span className="text-amber-400 font-bold shrink-0">②</span>V-Pass 조업 선박 긴급 귀항 유도 문자 발송</li>
                  <li className="flex items-start gap-2"><span className="text-slate-400 font-bold shrink-0">③</span>VHF Ch.16 기상 경보 방송 즉시 송출</li>
                </ul>
              </div>
            </div>

            {/* 하단 버튼 */}
            <div className="px-6 py-4 border-t border-navy-700 flex justify-end">
              <button
                onClick={() => { emergencyActiveRef.current = false; setEmergencyPhase('idle'); }}
                className="text-sm px-5 py-2 rounded-lg bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-500/40 transition font-semibold"
              >
                경보 확인
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DriGauge({ score, peakTime }: { score: number; peakTime: string }) {
  const pct   = Math.round(score * 100);
  const color = pct >= 60 ? "#ef4444" : pct >= 30 ? "#f59e0b" : "#22c55e";
  const label = pct >= 60 ? "고위험" : pct >= 30 ? "주의" : "정상";
  const peakLabel = new Date(peakTime).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
  return (
    <div className="flex flex-col items-center gap-2">
      <span className="text-lg font-bold px-4 py-1 rounded-full"
        style={{ color, background: `${color}20`, border: `1px solid ${color}50` }}>
        {label}
      </span>
      <p className="text-[11px] text-slate-400">
        최고 위험 예상 <span className="font-semibold" style={{ color }}>{peakLabel}</span>
      </p>
    </div>
  );
}

function GridCounts({ forecast, inline }: { forecast: RiskForecastResult; inline?: boolean }) {
  const counts = forecast.risk_grid.features.reduce(
    (acc, f) => {
      const lvl = (f.properties as RiskGridCellProperties).risk_level as RiskLevel;
      acc[lvl] = (acc[lvl] ?? 0) + 1;
      return acc;
    },
    {} as Record<RiskLevel, number>,
  );
  if (inline) {
    return (
      <>
        {(["고위험", "주의", "관찰"] as RiskLevel[]).map((lvl) => (
          <span key={lvl} className="flex items-center gap-1 shrink-0">
            <span className="text-slate-500 whitespace-nowrap">{RISK_LABEL[lvl]}</span>
            <span className="font-mono font-semibold whitespace-nowrap" style={{ color: RISK_COLOR[lvl] }}>
              {counts[lvl] ?? 0}셀
            </span>
          </span>
        ))}
      </>
    );
  }
  return (
    <>
      {(["고위험", "주의", "관찰"] as RiskLevel[]).map((lvl) => (
        <div key={lvl} className="flex justify-between gap-4">
          <span className="text-slate-500">{RISK_LABEL[lvl]}</span>
          <span className="font-mono font-semibold" style={{ color: RISK_COLOR[lvl] }}>
            {counts[lvl] ?? 0}셀
          </span>
        </div>
      ))}
    </>
  );
}
