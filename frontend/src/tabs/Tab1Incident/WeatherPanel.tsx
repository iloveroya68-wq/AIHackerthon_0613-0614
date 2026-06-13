import { useIncidentStore } from "@/store/incidentStore";

const DIRS16 = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];

function compass(deg: number) {
  return DIRS16[Math.round(((deg % 360) + 360) / 22.5) % 16];
}

function condition(ms: number): { label: string; color: string; detail: string } {
  if (ms >= 15) {
    return { label: "Limited", color: "#ef4444", detail: "Strong wind may limit small-vessel search." };
  }
  if (ms >= 10) {
    return { label: "Caution", color: "#f97316", detail: "Weather may reduce search efficiency." };
  }
  return { label: "Good", color: "#22c55e", detail: "Wind conditions are suitable for search." };
}

function Metric({
  label,
  value,
  unit,
  sub,
}: {
  label: string;
  value: string;
  unit: string;
  sub: string;
}) {
  return (
    <div className="px-4 py-3 border-t border-navy-700">
      <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">{label}</p>
      <div className="flex items-end justify-between">
        <div>
          <span className="text-2xl font-bold font-mono text-slate-200">{value}</span>
          <span className="text-xs text-slate-500 ml-1">{unit}</span>
        </div>
        <p className="text-xs font-semibold text-slate-300 text-right">{sub}</p>
      </div>
    </div>
  );
}

export function WeatherPanel() {
  const { prediction } = useIncidentStore();

  if (!prediction) {
    return (
      <aside className="w-64 shrink-0 flex flex-col items-center justify-center bg-navy-900 border-l border-navy-700 p-6 text-center text-slate-500 text-sm gap-3">
        <span className="text-3xl opacity-20">DRIFT</span>
        <p>Run a prediction to view environmental conditions.</p>
      </aside>
    );
  }

  const { drift_vector: dv } = prediction;
  const wind = condition(dv.wind_speed_ms);
  const windKt = (dv.wind_speed_ms * 1.94384).toFixed(1);

  return (
    <aside className="w-64 shrink-0 flex flex-col bg-navy-900 border-l border-navy-700 overflow-y-auto">
      <div className="px-4 py-2.5 border-b border-navy-700">
        <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
          Environment
        </span>
      </div>

      <div
        className="mx-3 mt-3 rounded-lg border px-3 py-2.5"
        style={{ borderColor: `${wind.color}40`, background: `${wind.color}15` }}
      >
        <div className="flex items-center gap-2 mb-1">
          <span className="w-2 h-2 rounded-full shrink-0" style={{ background: wind.color }} />
          <span className="text-xs font-bold" style={{ color: wind.color }}>
            Search {wind.label}
          </span>
        </div>
        <p className="text-[11px] leading-relaxed" style={{ color: `${wind.color}cc` }}>
          {wind.detail}
        </p>
      </div>

      <Metric
        label="Wind"
        value={dv.wind_speed_ms.toFixed(1)}
        unit="m/s"
        sub={`${compass(dv.wind_direction_deg)} ${dv.wind_direction_deg.toFixed(0)} deg (${windKt} kt)`}
      />
      <Metric
        label="Current"
        value={dv.current_speed_knots.toFixed(2)}
        unit="kt"
        sub={`${compass(dv.current_direction_deg)} ${dv.current_direction_deg.toFixed(0)} deg`}
      />
      <Metric
        label="Leeway"
        value={(dv.leeway_coefficient * 100).toFixed(1)}
        unit="%"
        sub="Vessel coefficient"
      />
    </aside>
  );
}
