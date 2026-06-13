import { useState } from "react";
import { useIncidentStore } from "@/store/incidentStore";
import { api } from "@/api";
import type { VesselType } from "@/types/contracts";

const VESSEL_TYPES: { type: VesselType; short: string }[] = [
  { type: "소형어선",      short: "소형어선" },
  { type: "표준어선",      short: "표준어선" },
  { type: "레저보트",      short: "레저보트" },
  { type: "구명조끼착용자", short: "구명조끼" },
  { type: "구명뗏목",      short: "구명뗏목" },
];

const TONNAGE_TYPES: VesselType[] = ["소형어선", "표준어선"];

const TIME_PRESETS: { label: string; offsetMs: number }[] = [
  { label: "지금",    offsetMs: 0 },
  { label: "30분 전", offsetMs: 30 * 60_000 },
  { label: "1시간",   offsetMs: 60 * 60_000 },
  { label: "2시간",   offsetMs: 2 * 60 * 60_000 },
  { label: "3시간",   offsetMs: 3 * 60 * 60_000 },
];

function toDatetimeLocalValue(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function fromDatetimeLocalValue(value: string): string | undefined {
  return value ? new Date(value).toISOString() : undefined;
}

export function InputPanel() {
  const {
    predictionRequest,
    setPredictionRequest,
    setPrediction,
    setIsSubmitting,
    isSubmitting,
    setSelectedTimeStepHour,
    mapPickMode,
    setMapPickMode,
  } = useIncidentStore();

  const [error, setError] = useState<string | null>(null);
  const [showNotes, setShowNotes] = useState(false);

  const coord = predictionRequest.last_coordinate;
  const vesselType = predictionRequest.vessel_type ?? "소형어선";
  const showTonnage = TONNAGE_TYPES.includes(vesselType);

  const setQuickTime = (offsetMs: number) => {
    setPredictionRequest({
      last_seen_at: new Date(Date.now() - offsetMs).toISOString(),
    });
  };

  const activePreset = TIME_PRESETS.find(({ offsetMs }) => {
    if (!predictionRequest.last_seen_at) return false;
    const diff = Math.abs(Date.now() - new Date(predictionRequest.last_seen_at).getTime() - offsetMs);
    return diff < 60_000;
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const defaultCoord = { lon: 126.2, lat: 34.5 };
      const actualCoord = predictionRequest.last_coordinate ?? defaultCoord;
      if (!predictionRequest.last_coordinate) {
        setPredictionRequest({ last_coordinate: actualCoord });
      }
      const req = {
        last_coordinate: actualCoord,
        last_seen_at: predictionRequest.last_seen_at ?? new Date().toISOString(),
        vessel_type: vesselType,
        vessel_id: predictionRequest.vessel_id ?? undefined,
        tonnage_tons: predictionRequest.tonnage_tons ?? undefined,
        simulation_hours: 24,
        notes: predictionRequest.notes ?? undefined,
      };
      const result = await api.createPrediction(req);
      setPrediction(result);
      setSelectedTimeStepHour(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "예측 요청 실패");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-4 p-4 bg-navy-900 border-r border-navy-700 w-72 shrink-0 overflow-y-auto"
    >
      <h2 className="text-sm font-semibold text-white uppercase tracking-wider">
        조난 정보 입력
      </h2>

      {/* ── 선종 버튼 그룹 ──────────────────────────────────────── */}
      <div className="flex flex-col gap-1.5">
        <label className="text-xs text-slate-400">선종 *</label>
        <div className="grid grid-cols-3 gap-1.5">
          {VESSEL_TYPES.map(({ type, short }) => {
            const active = vesselType === type;
            return (
              <button
                key={type}
                type="button"
                onClick={() => setPredictionRequest({ vessel_type: type })}
                className="py-1.5 rounded text-[11px] font-semibold transition-all border"
                style={
                  active
                    ? { background: "rgba(34,211,238,0.15)", borderColor: "#22d3ee", color: "#22d3ee" }
                    : { background: "rgba(15,23,42,0.6)", borderColor: "rgba(51,65,85,0.6)", color: "#64748b" }
                }
              >
                {short}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── 최종 신호 위치 ──────────────────────────────────────── */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <label className="text-xs text-slate-400">최종 신호 위치 *</label>
          <button
            type="button"
            onClick={() => setMapPickMode(!mapPickMode)}
            className="text-[10px] font-semibold px-2 py-0.5 rounded border transition-all"
            style={
              mapPickMode
                ? { background: "rgba(34,211,238,0.2)", borderColor: "#22d3ee", color: "#22d3ee" }
                : { background: "transparent", borderColor: "rgba(51,65,85,0.6)", color: "#64748b" }
            }
          >
            {mapPickMode ? "클릭 대기중…" : "지도에서 선택"}
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="flex flex-col gap-0.5">
            <span className="text-[10px] text-slate-600">경도 (°E)</span>
            <input
              type="number"
              step="0.0001"
              min="123"
              max="133"
              value={coord?.lon ?? ""}
              placeholder="126.2000"
              className="input-field"
              onChange={(e) => {
                const lon = Number(e.target.value);
                if (e.target.value && Number.isFinite(lon)) {
                  setPredictionRequest({
                    last_coordinate: {
                      lon: Number(lon.toFixed(4)),
                      lat: coord?.lat ?? 34.5,
                    },
                  });
                }
              }}
            />
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-[10px] text-slate-600">위도 (°N)</span>
            <input
              type="number"
              step="0.0001"
              min="32"
              max="40"
              value={coord?.lat ?? ""}
              placeholder="34.5000"
              className="input-field"
              onChange={(e) => {
                const lat = Number(e.target.value);
                if (e.target.value && Number.isFinite(lat)) {
                  setPredictionRequest({
                    last_coordinate: {
                      lon: coord?.lon ?? 126.2,
                      lat: Number(lat.toFixed(4)),
                    },
                  });
                }
              }}
            />
          </div>
        </div>
      </div>

      {/* ── 최종 신호 시각 ──────────────────────────────────────── */}
      <div className="flex flex-col gap-1.5">
        <label className="text-xs text-slate-400">최종 신호 시각</label>
        <div className="grid grid-cols-5 gap-1">
          {TIME_PRESETS.map(({ label, offsetMs }) => {
            const active = activePreset?.offsetMs === offsetMs;
            return (
              <button
                key={label}
                type="button"
                onClick={() => setQuickTime(offsetMs)}
                className="py-1 rounded text-[10px] font-semibold transition-all border"
                style={
                  active
                    ? { background: "rgba(34,211,238,0.15)", borderColor: "#22d3ee", color: "#22d3ee" }
                    : { background: "rgba(15,23,42,0.6)", borderColor: "rgba(51,65,85,0.6)", color: "#64748b" }
                }
              >
                {label}
              </button>
            );
          })}
        </div>
        <input
          type="datetime-local"
          value={toDatetimeLocalValue(predictionRequest.last_seen_at)}
          onChange={(e) =>
            setPredictionRequest({
              last_seen_at: fromDatetimeLocalValue(e.target.value),
            })
          }
          className="input-field text-xs"
        />
      </div>

      {/* ── 총톤수 (어선 선택 시에만) ───────────────────────────── */}
      {showTonnage && (
        <div className="flex flex-col gap-1">
          <label className="text-xs text-slate-400">총톤수 (GT)</label>
          <input
            type="number"
            step="0.1"
            min="0"
            placeholder="예: 29.0"
            value={predictionRequest.tonnage_tons ?? ""}
            onChange={(e) =>
              setPredictionRequest({
                tonnage_tons: e.target.value ? parseFloat(e.target.value) : undefined,
              })
            }
            className="input-field"
          />
        </div>
      )}

      {/* ── 현장 메모 (접기/펴기) ──────────────────────────────── */}
      <div>
        <button
          type="button"
          onClick={() => setShowNotes(!showNotes)}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-400 transition-colors"
        >
          <span
            className="inline-block transition-transform text-[10px]"
            style={{ transform: showNotes ? "rotate(90deg)" : "rotate(0deg)" }}
          >
            ▶
          </span>
          현장 메모
        </button>
        {showNotes && (
          <textarea
            rows={2}
            placeholder="추가 상황 정보..."
            value={predictionRequest.notes ?? ""}
            onChange={(e) => setPredictionRequest({ notes: e.target.value || undefined })}
            className="input-field resize-none mt-1.5 w-full"
          />
        )}
      </div>

      {error && (
        <p className="text-xs text-red-400 bg-red-400/10 rounded p-2">{error}</p>
      )}

      <button
        type="submit"
        disabled={isSubmitting}
        className={[
          "mt-auto w-full py-2.5 rounded text-sm font-semibold tracking-wide transition-all",
          isSubmitting
            ? "bg-navy-700 text-slate-500 cursor-not-allowed"
            : "bg-cyan-400 text-navy-950 hover:bg-cyan-300 shadow-glow",
        ].join(" ")}
      >
        {isSubmitting ? (
          <span className="flex items-center justify-center gap-2">
            <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            분석 중...
          </span>
        ) : "표류 예측 실행"}
      </button>
    </form>
  );
}
