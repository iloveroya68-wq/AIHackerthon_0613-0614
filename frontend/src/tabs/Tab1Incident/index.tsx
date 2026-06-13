import { useEffect, useState } from "react";
import { useIncidentStore } from "@/store/incidentStore";
import { DriftMap } from "@/map/MapProvider";
import { InputPanel } from "./InputPanel";
import { TimeSlider } from "./TimeSlider";
import { StatsBar } from "./StatsBar";
import { WeatherPanel } from "./WeatherPanel";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";

const ZONE_LEGEND = [
  { color: "#ef4444", label: "1순위" },
  { color: "#f97316", label: "2순위" },
  { color: "#eab308", label: "3순위" },
];

export function Tab1Incident() {
  const {
    prediction,
    selectedTimeStepHour,
    predictionRequest,
    mapPickMode,
    setMapPickMode,
    setPredictionRequest,
  } = useIncidentStore();
  const [hoverCoord, setHoverCoord] = useState<{ lat: number; lon: number } | null>(null);
  const [showEmptyState, setShowEmptyState] = useState(true);

  useEffect(() => {
    if (!mapPickMode) setHoverCoord(null);
  }, [mapPickMode]);

  const handleMapClick = mapPickMode
    ? (coord: { lat: number; lon: number }) => {
        setPredictionRequest({
          last_coordinate: {
            lat: Number(coord.lat.toFixed(4)),
            lon: Number(coord.lon.toFixed(4)),
          },
        });
        setMapPickMode(false);
      }
    : undefined;

  const handleMouseMove = mapPickMode
    ? (coord: { lat: number; lon: number }) => setHoverCoord(coord)
    : undefined;

  const currentStep = prediction?.time_steps?.find(
    (s) => s.hours === selectedTimeStepHour,
  );
  const isOrigin = selectedTimeStepHour === 0;
  const lastKnownPosition = predictionRequest.last_coordinate ?? undefined;

  const mapCenter: [number, number] = prediction
    ? isOrigin && lastKnownPosition
      ? [lastKnownPosition.lon, lastKnownPosition.lat]
      : [
          currentStep?.predicted_center.lon ?? prediction.predicted_center.lon,
          currentStep?.predicted_center.lat ?? prediction.predicted_center.lat,
        ]
    : [
        predictionRequest.last_coordinate?.lon ?? 127.0,
        predictionRequest.last_coordinate?.lat ?? 36.5,
      ];

  const activeZones = currentStep?.search_zones ?? prediction?.search_zones;
  const hasSearchZones = (activeZones?.features?.length ?? 0) > 0;
  const searchZones = isOrigin || !hasSearchZones ? undefined : activeZones;
  const particles = isOrigin ? undefined : currentStep?.debug_particles ?? undefined;
  const driftSector = prediction && lastKnownPosition
    ? {
        origin: lastKnownPosition,
        directionDeg: prediction.drift_vector.direction_deg,
        halfAngleDeg: 30,
        distanceNm: prediction.drift_vector.speed_knots * 24 * 3.5,
      }
    : undefined;

  return (
    <div
      className="flex flex-col flex-1 overflow-hidden"
      onPointerDown={() => {
        if (!prediction && showEmptyState) setShowEmptyState(false);
      }}
    >
      <div className="flex flex-1 overflow-hidden">
        <InputPanel />

        <div className="flex flex-col flex-1 overflow-hidden relative">
          <div className="flex-1 relative">
            <DriftMap
              center={mapCenter}
              zoom={prediction ? 10 : 8}
              searchZones={searchZones}
              lastKnownPosition={lastKnownPosition}
              driftSector={driftSector}
              particles={particles}
              onMapClick={handleMapClick}
              onMouseMove={handleMouseMove}
              pickMode={mapPickMode}
              className="h-full w-full"
            />

            {mapPickMode && (
              <div className="absolute inset-0 z-[1001] pointer-events-none flex items-start justify-center pt-6">
                <div className="flex flex-col items-center gap-1.5">
                  <div className="bg-cyan-400/90 text-navy-950 text-xs font-semibold px-4 py-2 rounded-full shadow-lg">
                    지도를 클릭해 최종 신호 위치 지정
                  </div>
                  {hoverCoord && (
                    <div className="bg-navy-950/90 border border-cyan-400/40 text-cyan-300 text-[11px] font-mono px-3 py-1.5 rounded-lg shadow-lg backdrop-blur-sm">
                      {hoverCoord.lat.toFixed(5)}N&nbsp;&nbsp;{hoverCoord.lon.toFixed(5)}E
                    </div>
                  )}
                </div>
              </div>
            )}

            {!prediction && showEmptyState && (
              <div className="absolute inset-0 flex items-center justify-center z-[999] pointer-events-none">
                <div
                  className="text-center bg-navy-900/90 rounded-2xl p-10 border border-navy-600/60 backdrop-blur-md shadow-[0_0_40px_rgba(0,0,0,0.5)]"
                  style={{
                    boxShadow:
                      "0 0 40px rgba(0,0,0,0.5), inset 0 0 1px rgba(34,211,238,0.1)",
                  }}
                >
                  <p className="text-sm font-semibold text-slate-200 mb-2 tracking-wide">
                    표류 예측을 시작하세요
                  </p>
                  <p className="text-xs text-slate-600 leading-relaxed">
                    좌측에서 조난 정보를 입력하고
                    <br />
                    표류 예측 실행 버튼을 클릭하세요
                  </p>
                </div>
              </div>
            )}

            {prediction && hasSearchZones && (
              <div className="absolute top-3 right-3 bg-navy-900/90 border border-navy-700 rounded-lg p-3 text-xs z-[1000]">
                <p className="text-slate-400 font-medium mb-2">수색 구역</p>
                {ZONE_LEGEND.map(({ color, label }) => (
                  <div key={label} className="flex items-center gap-2 mb-1 last:mb-0">
                    <span
                      className="w-3 h-3 rounded-sm border"
                      style={{ borderColor: color, backgroundColor: `${color}30` }}
                    />
                    <span className="text-slate-400">{label}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {prediction && <TimeSlider />}
          {prediction && <StatsBar />}
        </div>

        <WeatherPanel />
      </div>
      <DisclaimerBanner />
    </div>
  );
}
