import { useRef, useCallback } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useIncidentStore } from "@/store/incidentStore";
import { Header } from "@/components/Header";
import { TabBar } from "@/components/TabBar";
import { Tab1Incident } from "@/tabs/Tab1Incident";
import { Tab2Briefing } from "@/tabs/Tab2Briefing";
import { Tab3Risk } from "@/tabs/Tab3Risk";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

function AppContent() {
  const { activeTab, setActiveTab } = useIncidentStore();
  const emergencyRef = useRef<(() => void) | null>(null);
  const handleTabBarEmergency = useCallback(() => { emergencyRef.current?.(); }, []);
  const registerEmergency = useCallback((fn: () => void) => { emergencyRef.current = fn; }, []);

  return (
    <div className="flex flex-col h-screen bg-navy-950 text-slate-100 overflow-hidden">
      <Header />
      <TabBar active={activeTab} onChange={setActiveTab} onEmergency={handleTabBarEmergency} />
      <main className="flex flex-1 overflow-hidden">
        {activeTab === "incident" && <Tab1Incident />}
        {activeTab === "briefing" && <Tab2Briefing />}
        {activeTab === "risk" && <Tab3Risk onRegisterEmergency={registerEmergency} />}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
}
