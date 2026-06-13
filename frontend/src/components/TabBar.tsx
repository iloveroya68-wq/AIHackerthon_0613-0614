import type { AppTab } from "@/store/incidentStore";

interface Tab {
  id: AppTab;
  label: string;
  sublabel: string;
  icon: string;
}

const TABS: Tab[] = [
  {
    id: "incident",
    label: "실시간 조난 대응",
    sublabel: "Incident Response",
    icon: "🚨",
  },
  {
    id: "briefing",
    label: "AI 작전 브리핑",
    sublabel: "Operational Briefing",
    icon: "📋",
  },
  {
    id: "risk",
    label: "선제 위험 예측",
    sublabel: "Proactive Risk",
    icon: "⚠️",
  },
];

interface TabBarProps {
  active: AppTab;
  onChange: (tab: AppTab) => void;
  onEmergency?: () => void;
}

export function TabBar({ active, onChange, onEmergency }: TabBarProps) {
  return (
    <nav className="flex items-center border-b border-navy-700/80 bg-gradient-to-b from-navy-900 to-navy-950/80">
      {TABS.map((tab) => {
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={[
              "relative flex items-center gap-2.5 px-6 py-3 text-sm font-medium transition-all duration-200",
              "focus:outline-none",
              isActive
                ? "text-white border-b-2 border-cyan-400 bg-gradient-to-b from-navy-700/50 to-transparent"
                : "text-slate-400 border-b-2 border-transparent hover:text-slate-200 hover:bg-navy-800/30",
            ].join(" ")}
          >
            <span className={[
              "text-base leading-none transition-all duration-200",
              isActive ? "drop-shadow-[0_0_6px_rgba(0,212,255,0.6)]" : "opacity-60",
            ].join(" ")}>{tab.icon}</span>
            <span className="flex flex-col items-start">
              <span className="leading-tight">{tab.label}</span>
              <span className={[
                "text-[10px] leading-tight transition-colors duration-200",
                isActive ? "text-cyan-400/60" : "opacity-50",
              ].join(" ")}>{tab.sublabel}</span>
            </span>
            {isActive && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-cyan-400/0 via-cyan-400 to-cyan-400/0 shadow-[0_0_8px_rgba(0,212,255,0.6)]" />
            )}
          </button>
        );
      })}

      {active === "risk" && onEmergency && (
        <button
          onClick={onEmergency}
          className="ml-auto mr-4 flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-bold tracking-wide border border-red-500/50 bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-all"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
          비상상황시연
        </button>
      )}
    </nav>
  );
}
