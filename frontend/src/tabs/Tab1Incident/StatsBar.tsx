import { useIncidentStore } from "@/store/incidentStore";

const DIRS16 = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
function compass(deg: number) {
  return DIRS16[Math.round(((deg % 360) + 360) / 22.5) % 16];
}

function windLevel(ms: number): { dot: string; label: string } {
  if (ms >= 20) return { dot: "#ef4444", label: "Severe" };
  if (ms >= 15) return { dot: "#f97316", label: "Strong" };
  if (ms >= 10) return { dot: "#eab308", label: "Caution" };
  return { dot: "#22c55e", label: "Good" };
}

interface ItemProps {
  label: string;
  value: string;
  sub: string;
  warn?: { dot: string; label: string };
}

function Item({ label, value, sub, warn }: ItemProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-0.5 py-2.5 min-w-0">
      <span className="text-[10px] font-medium text-slate-400 uppercase tracking-widest truncate">
        {label}
      </span>
      <div className="flex items-baseline gap-1">
        <span className="text-sm font-bold font-mono text-slate-200 leading-tight">
          {value}
        </span>
        {warn && (
          <span
            className="text-[9px] font-semibold px-1 py-0.5 rounded"
            style={{ color: warn.dot, background: `${warn.dot}18` }}
          >
            {warn.label}
          </span>
        )}
      </div>
      <span className="text-[10px] text-slate-500 font-mono truncate">{sub}</span>
    </div>
  );
}

function Divider() {
  return <div className="w-px self-stretch my-2 bg-navy-700/60 shrink-0" />;
}

export function StatsBar() {
  const { prediction, selectedTimeStepHour } = useIncidentStore();
  if (!prediction) return null;

  const { drift_vector: dv } = prediction;
  const currentStep = prediction.time_steps?.find((s) => s.hours === selectedTimeStepHour);
  const zone1 = currentStep?.search_zones.features.find((f) => f.properties.priority === 1)
    ?? prediction.search_zones.features.find((f) => f.properties.priority === 1);
  const distNm = (currentStep?.drift_distance_nm ?? 0).toFixed(1);
  const wind = windLevel(dv.wind_speed_ms);

  return (
    <div className="flex items-stretch border-t border-navy-700/60 bg-navy-900">
      <Item
        label={`+${selectedTimeStepHour}h drift distance`}
        value={`${distNm} NM`}
        sub={`${(parseFloat(distNm) * 1.852).toFixed(1)} km`}
      />
      <Divider />
      <Item
        label="Wind"
        value={`${dv.wind_speed_ms.toFixed(1)} m/s`}
        sub={`${compass(dv.wind_direction_deg)} ${dv.wind_direction_deg.toFixed(0)} deg`}
        warn={dv.wind_speed_ms >= 10 ? wind : undefined}
      />
      <Divider />
      <Item
        label="Current"
        value={`${dv.current_speed_knots.toFixed(2)} kt`}
        sub={`${compass(dv.current_direction_deg)} ${dv.current_direction_deg.toFixed(0)} deg`}
      />
      <Divider />
      <Item
        label="Priority 1"
        value={`${((zone1?.properties.cumulative_probability ?? 0) * 100).toFixed(0)}%`}
        sub="OpenDrift zone"
      />
    </div>
  );
}
