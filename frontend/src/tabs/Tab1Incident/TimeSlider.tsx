import { useIncidentStore } from "@/store/incidentStore";

export function TimeSlider() {
  const { prediction, selectedTimeStepHour, setSelectedTimeStepHour } = useIncidentStore();

  if (!prediction) return null;

  const availableMaxHours = prediction.time_steps?.at(-1)?.hours ?? prediction.time_horizon_hours;
  const maxHours = Math.max(1, availableMaxHours);
  const currentStep = prediction.time_steps?.find((s) => s.hours === selectedTimeStepHour);

  // 0h = 최종 신호 위치 (원점), 이후는 time_steps
  const isOrigin = selectedTimeStepHour === 0;
  const distNm = isOrigin ? "0.0" : (currentStep?.drift_distance_nm ?? 0).toFixed(1);
  const pos = isOrigin
    ? null
    : currentStep?.predicted_center ?? null;

  // Ticks: 0, 4, 8, 12, 16, 20, 24
  const ticks = [0, ...Array.from({ length: maxHours }, (_, i) => i + 1).filter(
    (h) => h % 4 === 0 || h === maxHours
  )];

  const pct = (selectedTimeStepHour / maxHours) * 100;

  return (
    <div className="bg-navy-900 border-t border-navy-700 px-5 py-3">
      {/* Top row */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] text-slate-500 uppercase tracking-wider">
          표류 예측 시간대
        </span>
        <div className="flex items-center gap-3 text-xs text-slate-400">
          <span>
            표류거리&nbsp;
            <span className="font-mono text-cyan-400">{distNm} NM</span>
          </span>
          {pos && (
            <>
              <span className="text-slate-600">|</span>
              <span>
                {isOrigin ? "최종 신호 위치" : "예측 위치"}&nbsp;
                <span className="font-mono text-cyan-400">
                  {pos.lat.toFixed(4)}°N&nbsp;{pos.lon.toFixed(4)}°E
                </span>
              </span>
            </>
          )}
        </div>
        <span className="text-sm font-mono font-bold text-cyan-400 bg-navy-800 border border-navy-600 rounded px-2 py-0.5">
          {isOrigin ? "0h (원점)" : `+${selectedTimeStepHour}h`}
        </span>
      </div>

      {/* Slider */}
      <input
        type="range"
        min="0"
        max={maxHours}
        step="1"
        value={selectedTimeStepHour}
        onChange={(e) => setSelectedTimeStepHour(parseInt(e.target.value))}
        className="w-full accent-cyan-400 cursor-pointer"
      />

      {/* Tick labels */}
      <div className="relative h-4 mt-0.5">
        {ticks.map((h) => {
          const left = (h / maxHours) * 100;
          return (
            <span
              key={h}
              className="absolute text-[9px] text-slate-600 -translate-x-1/2"
              style={{ left: `${left}%` }}
            >
              {h}h
            </span>
          );
        })}
      </div>

      {/* Progress track */}
      <div className="mt-1 h-0.5 bg-navy-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-cyan-400/40 rounded-full transition-all duration-150"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
