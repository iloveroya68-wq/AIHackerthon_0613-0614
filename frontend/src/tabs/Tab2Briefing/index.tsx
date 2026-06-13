import { useState, useRef, useEffect } from "react";
import { useIncidentStore } from "@/store/incidentStore";
import { api } from "@/api";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";
import { DriftMap } from "@/map/MapProvider";
import { gmsChat, type ChatMessage } from "@/api/gms/client";
import type { EnginePredictionResult, BriefingResult, PredictionRequest } from "@/types/contracts";

const DIRS16 = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
function deg2compass(deg: number) {
  return DIRS16[Math.round(((deg % 360) + 360) / 22.5) % 16];
}

function windMeta(ms: number): { label: string; color: string } {
  if (ms >= 20) return { label: "폭풍", color: "#ef4444" };
  if (ms >= 15) return { label: "강풍", color: "#f97316" };
  if (ms >= 10) return { label: "중풍", color: "#eab308" };
  return { label: "약풍", color: "#22c55e" };
}

function elapsedLabel(since: string): string {
  const diff = Date.now() - new Date(since).getTime();
  const h = Math.floor(diff / 3_600_000);
  const m = Math.floor((diff % 3_600_000) / 60_000);
  if (h === 0) return `${m}분 경과`;
  return `${h}시간 ${m}분 경과`;
}

function DataRow({ label, value, sub, color = "#e2e8f0" }: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="flex items-baseline justify-between py-1.5 border-b border-navy-700/50 last:border-0">
      <span className="text-[11px] text-slate-500 shrink-0">{label}</span>
      <div className="text-right">
        <span className="text-xs font-mono font-semibold" style={{ color }}>{value}</span>
        {sub && <span className="block text-[10px] text-slate-600">{sub}</span>}
      </div>
    </div>
  );
}

const SECTION_META = [
  { num: "01", color: "#ef4444", bg: "#ef444412", border: "#ef444428" },
  { num: "02", color: "#3b82f6", bg: "#3b82f612", border: "#3b82f628" },
  { num: "03", color: "#22d3ee", bg: "#22d3ee10", border: "#22d3ee28" },
  { num: "04", color: "#f59e0b", bg: "#f59e0b10", border: "#f59e0b28" },
];

function SectionCard({
  section, meta,
}: {
  section: BriefingResult["sections"][number];
  meta: typeof SECTION_META[number];
}) {
  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{ background: meta.bg, borderColor: meta.border }}
    >
      <div
        className="flex items-center gap-3 px-4 py-2.5 border-b"
        style={{ borderColor: meta.border, background: `${meta.color}08` }}
      >
        <span
          className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold font-mono"
          style={{ background: meta.color, color: "#0a1628" }}
        >
          {meta.num}
        </span>
        <p className="flex-1 text-sm font-semibold text-slate-100 leading-snug">{section.title}</p>
      </div>
      <div className="px-4 py-3.5">
        <p className="text-[13px] text-slate-300 leading-relaxed">{section.body}</p>
      </div>
    </div>
  );
}

function Spinner({ small }: { small?: boolean }) {
  return (
    <svg
      className={`animate-spin text-cyan-400 ${small ? "h-4 w-4" : "h-5 w-5"}`}
      fill="none" viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

export function Tab2Briefing() {
  const {
    prediction, predictionRequest,
    briefing, setBriefing,
    isBriefingLoading, setIsBriefingLoading,
    setActiveTab,
  } = useIncidentStore();

  const handleGenerate = async () => {
    if (!prediction) return;
    setIsBriefingLoading(true);
    try {
      const result = await api.createBriefing(prediction.request_id);
      setBriefing(result);
    } finally {
      setIsBriefingLoading(false);
    }
  };

  if (!prediction) {
    return (
      <div className="flex flex-col flex-1 items-center justify-center gap-4 text-slate-500">
        <div className="text-center">
          <p className="font-medium text-slate-400 mb-1">표류 예측이 없습니다</p>
          <p className="text-sm text-slate-600">
            먼저{" "}
            <button onClick={() => setActiveTab("incident")} className="text-cyan-400 underline">
              실시간 조난 대응
            </button>{" "}
            탭에서 예측을 실행하세요
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <BriefingLayout
        prediction={prediction}
        predictionRequest={predictionRequest}
        briefing={briefing}
        onGenerate={handleGenerate}
        isLoading={isBriefingLoading}
      />
      <div className="flex items-center gap-2.5 px-4 py-1.5 bg-navy-950 border-t border-navy-700 text-[10px] font-mono shrink-0">
        <span
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{ background: prediction.data_freshness_ok ? "#22c55e" : "#f59e0b" }}
        />
        <span className="text-slate-500">
          데이터 {prediction.data_freshness_ok ? "실시간" : "백업"} ·{" "}
          {prediction.current_data_source ?? "KHOA"} · {prediction.weather_data_source ?? "KMA"}
        </span>
        <div className="flex-1" />
        <span className="text-slate-700 hidden lg:block">
          최종 판단은 현장 지휘관 책임 하에 이루어져야 합니다
        </span>
      </div>
      {briefing && <DisclaimerBanner text={briefing.disclaimer} />}
    </div>
  );
}

function BriefingLayout({
  prediction, predictionRequest, briefing, onGenerate, isLoading,
}: {
  prediction: EnginePredictionResult;
  predictionRequest: Partial<PredictionRequest>;
  briefing: BriefingResult | null;
  onGenerate: () => void;
  isLoading: boolean;
}) {
  const dv = prediction.drift_vector;
  const { label: wLabel, color: wColor } = windMeta(dv.wind_speed_ms);
  const origin = predictionRequest.last_coordinate;
  const lastSeenAt = predictionRequest.last_seen_at;

  const mapCenter: [number, number] = [
    prediction.predicted_center.lon,
    prediction.predicted_center.lat,
  ];

  const incidentTime = lastSeenAt
    ? new Date(lastSeenAt).toLocaleString("ko-KR", {
        month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit",
      })
    : "—";

  const elapsed = lastSeenAt ? elapsedLabel(lastSeenAt) : null;

  const features = prediction.search_zones.features as any[];
  const zone1 = features.find((f) => f.properties.priority === 1);
  const zone2 = features.find((f) => f.properties.priority === 2);
  const zone3 = features.find((f) => f.properties.priority === 3);

  return (
    <div className="flex flex-1 overflow-hidden">

      {/* ── Left sidebar ─────────────────────────────────────────────── */}
      <aside className="w-72 shrink-0 border-r border-navy-700 bg-navy-900 flex flex-col overflow-y-auto">

        <div className="shrink-0 border-b border-navy-700" style={{ height: 200 }}>
          <DriftMap
            center={mapCenter}
            zoom={10}
            searchZones={prediction.search_zones}
            lastKnownPosition={origin}
            className="h-full w-full"
          />
        </div>

        <div className="flex flex-col gap-4 p-4 overflow-y-auto">

          {/* Incident summary */}
          <section>
            <h3 className="text-[10px] font-semibold text-cyan-400 uppercase tracking-wider mb-2">
              상황 요약
            </h3>
            <DataRow label="선종" value={predictionRequest.vessel_type ?? "—"} />
            {predictionRequest.vessel_id && (
              <DataRow label="선박 ID" value={predictionRequest.vessel_id} color="#94a3b8" />
            )}
            <DataRow label="최종 신호" value={incidentTime} color="#f59e0b" />
            {elapsed && (
              <DataRow label="경과 시간" value={elapsed} color="#ef4444" />
            )}
            {origin && (
              <DataRow
                label="실종 좌표"
                value={`${origin.lat.toFixed(4)}°N`}
                sub={`${origin.lon.toFixed(4)}°E`}
                color="#f59e0b"
              />
            )}
          </section>

          {/* Priority search zones */}
          <section>
            <h3 className="text-[10px] font-semibold text-cyan-400 uppercase tracking-wider mb-2">
              수색 우선구역
            </h3>

            {/* Zone 1 — prominent with coordinates */}
            {zone1 && (
              <div className="mb-3 p-2.5 rounded-lg border border-red-400/25 bg-red-400/5">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] font-bold text-red-400">1순위 구역</span>
                  <span className="text-[11px] font-mono font-bold text-red-300">
                    조난자 {Math.round(zone1.properties.cumulative_probability * 100)}%
                  </span>
                </div>
                <p className="text-[9px] text-red-400/70 mb-1.5">이 구역 안에 있을 확률</p>
                <p className="text-[11px] font-mono text-slate-200">
                  {zone1.properties.center_lat.toFixed(4)}°N
                </p>
                <p className="text-[11px] font-mono text-slate-200">
                  {zone1.properties.center_lon.toFixed(4)}°E
                </p>
                <p className="text-[9px] text-slate-500 mt-1">
                  {zone1.properties.area_km2.toFixed(1)} km² · 반경 {zone1.properties.radius_km.toFixed(1)} km
                </p>
              </div>
            )}

            {/* Zone 2, 3 — marginal probability */}
            {[
              { label: "2순위", zone: zone2, prev: zone1, color: "#f97316" },
              { label: "3순위", zone: zone3, prev: zone2, color: "#eab308" },
            ].map(({ label, zone, prev, color }) => {
              if (!zone) return null;
              const cumProb = Math.round(zone.properties.cumulative_probability * 100);
              const marginal = prev
                ? Math.round((zone.properties.cumulative_probability - prev.properties.cumulative_probability) * 100)
                : cumProb;
              return (
                <div key={label} className="flex items-center gap-2 py-1.5 border-b border-navy-700/50 last:border-0">
                  <span className="text-[10px] font-semibold w-10 shrink-0" style={{ color }}>{label}</span>
                  <div className="flex-1 h-1.5 bg-navy-700 rounded-full overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${marginal}%`, background: color }} />
                  </div>
                  <span className="text-[10px] font-mono text-slate-400 shrink-0 text-right">
                    +{marginal}%
                  </span>
                </div>
              );
            })}

            <div className="mt-2 pt-2 border-t border-navy-700/50">
              <DataRow
                label="표류 방향"
                value={`${dv.direction_deg.toFixed(0)}° ${deg2compass(dv.direction_deg)}`}
              />
              <DataRow label="표류 속도" value={`${dv.speed_knots.toFixed(2)} kt`} />
            </div>
          </section>

          {/* Current sea & weather conditions */}
          <section>
            <h3 className="text-[10px] font-semibold text-cyan-400 uppercase tracking-wider mb-2">
              현재 해양·기상
            </h3>
            <DataRow
              label="풍속"
              value={`${dv.wind_speed_ms.toFixed(1)} m/s`}
              sub={`${wLabel} · ${deg2compass(dv.wind_direction_deg)}`}
              color={wColor}
            />
            <DataRow
              label="조류"
              value={`${dv.current_speed_knots.toFixed(2)} kt`}
              sub={deg2compass(dv.current_direction_deg)}
              color="#a78bfa"
            />
            {dv.wind_speed_ms >= 10 && (
              <div className="mt-2 flex items-center gap-1.5 px-2 py-1.5 rounded bg-amber-400/10 border border-amber-400/25">
                <span className="text-[9px] font-semibold text-amber-400">
                  ⚠️ {dv.wind_speed_ms >= 15 ? "강풍 경보 — 항공 전력 검토" : "기상 주의 — 수색 조건 모니터링"}
                </span>
              </div>
            )}
          </section>

        </div>
      </aside>

      {/* ── Main content ─────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">

        {/* Sticky header */}
        <div className="sticky top-0 z-10 bg-navy-950 border-b border-navy-700 px-6 py-3 flex items-center gap-4">
          <div className="flex-1 min-w-0">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              AI 작전 브리핑
            </span>
            {briefing && (
              <span className="ml-3 text-[11px] text-slate-600">
                생성: {new Date(briefing.generated_at).toLocaleString("ko-KR")}
              </span>
            )}
          </div>

          {/* Elapsed time — operationally critical */}
          {elapsed && (
            <div className="flex items-center gap-1.5 shrink-0 bg-red-400/10 border border-red-400/25 rounded px-2.5 py-1">
              <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse shrink-0" />
              <span className="text-xs font-semibold text-red-300">{elapsed}</span>
            </div>
          )}

          {briefing && (
            <div className="flex items-center gap-4 shrink-0">
              <span className={[
                "text-xs font-semibold px-2.5 py-1 rounded border",
                briefing.confidence_label === "높음"
                  ? "text-green-400 border-green-400/30 bg-green-400/10"
                  : briefing.confidence_label === "보통"
                  ? "text-amber-400 border-amber-400/30 bg-amber-400/10"
                  : "text-red-400 border-red-400/30 bg-red-400/10",
              ].join(" ")}>
                신뢰도 {briefing.confidence_label}
              </span>
              {briefing.pdf_url ? (
                <a
                  href={briefing.pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-cyan-400/40 text-cyan-400 text-xs font-semibold hover:bg-cyan-400/10 transition-colors shrink-0"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 12h8M8 3v7m-3-3 3 3 3-3" />
                    <path strokeLinecap="round" d="M2 13.5h12" />
                  </svg>
                  PDF 내보내기
                </a>
              ) : (
                <span className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-navy-600 text-slate-600 text-xs cursor-not-allowed shrink-0">
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 12h8M8 3v7m-3-3 3 3 3-3" />
                    <path strokeLinecap="round" d="M2 13.5h12" />
                  </svg>
                  PDF 내보내기
                </span>
              )}
            </div>
          )}
        </div>

        <div className="p-6 flex flex-col gap-6">

          {/* Generate button */}
          {!briefing && (
            <div className="flex flex-col items-center py-10 gap-4 border border-dashed border-navy-600 rounded-xl">
              <div className="text-center mb-2">
                <p className="text-sm font-semibold text-slate-300 mb-1">AI 작전 브리핑 생성</p>
                <p className="text-xs text-slate-500">
                  표류 예측 결과를 바탕으로 해경 수색 작전 브리핑을 생성합니다
                </p>
              </div>
              <button
                onClick={onGenerate}
                disabled={isLoading}
                className="px-8 py-3 rounded-lg bg-cyan-400 text-navy-950 font-bold text-sm hover:bg-cyan-300 shadow-glow disabled:opacity-50 transition-all"
              >
                {isLoading ? (
                  <span className="flex items-center gap-2.5"><Spinner small />브리핑 생성 중…</span>
                ) : "브리핑 생성하기"}
              </button>
            </div>
          )}

          {/* Briefing sections */}
          {briefing && (
            <div className="flex flex-col gap-3">
              {briefing.sections.map((section, i) => (
                <SectionCard
                  key={section.section_id}
                  section={section}
                  meta={SECTION_META[i] ?? SECTION_META[0]}
                />
              ))}
            </div>
          )}

          {/* SAR Chatbot */}
          {briefing && (
            <SARChatbot
              prediction={prediction}
              predictionRequest={predictionRequest}
              briefing={briefing}
            />
          )}

        </div>
      </div>
    </div>
  );
}

// ── GMS system prompt builder ─────────────────────────────────────────────

function buildSystemPrompt(
  prediction: EnginePredictionResult,
  predictionRequest: Partial<PredictionRequest>,
  briefing: BriefingResult,
): string {
  const dv = prediction.drift_vector;
  const features = prediction.search_zones.features as any[];
  const z1 = features.find((f) => f.properties.priority === 1);
  const z2 = features.find((f) => f.properties.priority === 2);
  const origin = predictionRequest.last_coordinate;
  const distKm = (dv.speed_knots * 1.852 * prediction.time_horizon_hours).toFixed(1);

  const waveH = (0.025 * Math.pow(dv.wind_speed_ms, 1.7)).toFixed(1);
  const marginal2 = z1 && z2
    ? Math.round((z2.properties.cumulative_probability - z1.properties.cumulative_probability) * 100)
    : 0;

  return `당신은 대한민국 해양경찰 수색구조(SAR) 현장 작전 지원 AI입니다.

[역할과 원칙]
- 현장 지휘관(함장·작전관)에게 즉시 적용 가능한 답변을 제공합니다.
- 반드시 아래 [현재 사건 데이터]를 기반으로 답변하고, 수치는 구체적으로 인용하세요.
- 단계별 행동 지침(▶ 형식), 중요 수치 강조, 판단 근거를 함께 제시하세요.
- "~할 수 있습니다" 같은 모호한 표현 대신 "~하십시오", "~권고합니다" 등 명확한 지시형으로 답변하세요.
- 답변 길이: 질문 성격에 따라 조절하되, 핵심 행동 지침은 반드시 포함하세요.
- 언어: 한국어, 해양경찰 작전 용어 사용.

[현재 사건 데이터]
선종: ${predictionRequest.vessel_type ?? "미상"}
최종 신호 위치: ${origin ? `${origin.lat.toFixed(4)}°N, ${origin.lon.toFixed(4)}°E` : "미상"}
현재 추정 위치(1순위 구역 중심): ${prediction.predicted_center.lat.toFixed(4)}°N, ${prediction.predicted_center.lon.toFixed(4)}°E
최종 교신 후 경과: ${prediction.time_horizon_hours}시간
표류 벡터: ${dv.direction_deg.toFixed(0)}° 방향 / ${dv.speed_knots.toFixed(2)} kt / ${distKm} km 이동

풍속: ${dv.wind_speed_ms.toFixed(1)} m/s (${deg2compass(dv.wind_direction_deg)}풍) / 추정 파고 ${waveH} m
조류: ${dv.current_speed_knots.toFixed(2)} kt (${deg2compass(dv.current_direction_deg)} 방향)
데이터: ${prediction.data_freshness_ok ? "실시간" : "백업 (정확도 주의)"}

1순위 구역: ${z1 ? `${z1.properties.center_lat.toFixed(4)}°N, ${z1.properties.center_lon.toFixed(4)}°E — 조난자 위치 확률 ${Math.round(z1.properties.cumulative_probability * 100)}%, 면적 ${z1.properties.area_km2.toFixed(1)} km², 반경 ${z1.properties.radius_km.toFixed(1)} km` : "미정"}
2순위 구역: ${z2 ? `${z2.properties.center_lat.toFixed(4)}°N, ${z2.properties.center_lon.toFixed(4)}°E — 추가 확률 +${marginal2}% (누적 ${Math.round(z2.properties.cumulative_probability * 100)}%)` : "미정"}
위험도 점수: ${briefing.risk_score}/100 | 분석 신뢰도: ${briefing.confidence_label}

[AI 브리핑 분석 결과]
${briefing.sections.map((s) => `■ ${s.title}\n${s.body}`).join("\n\n")}`;
}

// ── Quick question chips ──────────────────────────────────────────────────

const QUICK_QUESTIONS = [
  "지금 당장 해야 할 행동 3가지",
  "이 기상에서 수색 가능한가?",
  "생존 가능 시간이 얼마나 남았나?",
  "1순위 수색 완료 후 다음 행동은?",
  "야간 수색 전환 시 주의사항",
];

const SUMMARY_PROMPT =
  "현재 조난 사건을 종합 분석하여 다음 항목으로 브리핑하세요:\n" +
  "1) 현재 상황 요약 (위치, 표류 거리, 경과 시간, 생존 가능성)\n" +
  "2) 지금 즉시 취해야 할 행동 3가지 (구체적 수치 포함)\n" +
  "3) 가장 주의해야 할 위험 요소\n" +
  "4) 수색 성공 가능성을 높이는 핵심 조건";

// ── SAR Chatbot ───────────────────────────────────────────────────────────

function SARChatbot({
  prediction, predictionRequest, briefing,
}: {
  prediction: EnginePredictionResult;
  predictionRequest: Partial<PredictionRequest>;
  briefing: BriefingResult;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const systemPrompt = buildSystemPrompt(prediction, predictionRequest, briefing);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (text: string) => {
    if (!text.trim() || loading) return;
    setError(null);
    const userMsg: ChatMessage = { role: "user", text: text.trim() };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput("");
    setLoading(true);
    try {
      const reply = await gmsChat(systemPrompt, messages, text.trim());
      setMessages([...next, { role: "model", text: reply }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "GMS API 오류");
    } finally {
      setLoading(false);
    }
  };

  const started = messages.length > 0;

  return (
    <div className="border border-navy-700 rounded-xl overflow-hidden">

      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 bg-navy-800 border-b border-navy-700">
        <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse shrink-0" />
        <div className="flex-1">
          <p className="text-sm font-semibold text-slate-200">최종 종합 분석 / 상황 질문</p>
          <p className="text-[10px] text-slate-500">GMS GPT-4.1 · 현재 사건 컨텍스트 기반</p>
        </div>
        {started && (
          <button
            onClick={() => { setMessages([]); setError(null); }}
            className="text-[10px] text-slate-600 hover:text-slate-400 transition-colors"
          >
            초기화
          </button>
        )}
      </div>

      {/* Not started: summary trigger */}
      {!started && (
        <div className="flex flex-col items-center gap-4 py-10 px-6 bg-navy-900/60">
          <p className="text-xs text-slate-500 text-center">
            현재 사건 전체 컨텍스트를 바탕으로 AI가 종합 요약을 제공하고<br />
            추가 질문에 답변합니다
          </p>
          <button
            onClick={() => send(SUMMARY_PROMPT)}
            disabled={loading}
            className="px-6 py-2.5 rounded-lg bg-cyan-400 text-navy-950 font-bold text-sm hover:bg-cyan-300 disabled:opacity-50 transition-all"
          >
            {loading
              ? <span className="flex items-center gap-2"><Spinner small />분석 중…</span>
              : "AI 종합 분석 시작"}
          </button>
        </div>
      )}

      {/* Message list */}
      {started && (
        <div className="flex flex-col max-h-96 overflow-y-auto bg-navy-950 px-4 py-4 gap-4">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex gap-2.5 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}
            >
              {/* Avatar */}
              <div
                className="shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-bold mt-0.5"
                style={
                  msg.role === "user"
                    ? { background: "rgba(34,211,238,0.2)", color: "#22d3ee" }
                    : { background: "rgba(99,102,241,0.2)", color: "#818cf8" }
                }
              >
                {msg.role === "user" ? "나" : "AI"}
              </div>
              {/* Bubble */}
              <div
                className="max-w-[85%] rounded-xl px-3.5 py-2.5 text-[13px] leading-relaxed whitespace-pre-wrap"
                style={
                  msg.role === "user"
                    ? { background: "rgba(34,211,238,0.12)", color: "#e2e8f0", borderRadius: "12px 4px 12px 12px" }
                    : { background: "rgba(15,23,42,0.8)", border: "1px solid rgba(51,65,85,0.5)", color: "#cbd5e1", borderRadius: "4px 12px 12px 12px" }
                }
              >
                {msg.text}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex gap-2.5">
              <div className="shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-bold" style={{ background: "rgba(99,102,241,0.2)", color: "#818cf8" }}>AI</div>
              <div className="flex items-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-navy-800/80 border border-navy-700">
                {[0,1,2].map((i) => (
                  <span key={i} className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: `${i * 150}ms` }} />
                ))}
              </div>
            </div>
          )}

          {error && (
            <p className="text-xs text-red-400 bg-red-400/10 rounded px-3 py-2">{error}</p>
          )}

          <div ref={bottomRef} />
        </div>
      )}

      {/* Quick question chips */}
      {started && (
        <div className="flex flex-wrap gap-1.5 px-4 py-2.5 bg-navy-900 border-t border-navy-800">
          {QUICK_QUESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => send(q)}
              disabled={loading}
              className="text-[10px] px-2.5 py-1 rounded-full border border-navy-600 text-slate-500 hover:border-cyan-400/50 hover:text-cyan-400 disabled:opacity-40 transition-all"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Input field */}
      {started && (
        <div className="flex gap-2 px-4 py-3 bg-navy-900 border-t border-navy-700">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send(input)}
            placeholder="질문을 입력하세요…"
            disabled={loading}
            className="flex-1 bg-navy-800 border border-navy-600 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-400/50 transition-colors disabled:opacity-50"
          />
          <button
            onClick={() => send(input)}
            disabled={loading || !input.trim()}
            className="px-3 py-2 rounded-lg bg-cyan-400 text-navy-950 font-bold text-xs hover:bg-cyan-300 disabled:opacity-40 transition-all shrink-0"
          >
            전송
          </button>
        </div>
      )}
    </div>
  );
}
