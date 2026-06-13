import { create } from "zustand";
import type { EnginePredictionResult, BriefingResult, PredictionRequest } from "@/types/contracts";

export type AppTab = "incident" | "briefing" | "risk";

interface IncidentState {
  activeTab: AppTab;
  setActiveTab: (tab: AppTab) => void;

  predictionRequest: Partial<PredictionRequest>;
  setPredictionRequest: (req: Partial<PredictionRequest>) => void;

  prediction: EnginePredictionResult | null;
  setPrediction: (p: EnginePredictionResult | null) => void;

  briefing: BriefingResult | null;
  setBriefing: (b: BriefingResult | null) => void;

  selectedTimeStepHour: number;
  setSelectedTimeStepHour: (h: number) => void;

  isSubmitting: boolean;
  setIsSubmitting: (v: boolean) => void;

  isBriefingLoading: boolean;
  setIsBriefingLoading: (v: boolean) => void;

  mapPickMode: boolean;
  setMapPickMode: (v: boolean) => void;
}

export const useIncidentStore = create<IncidentState>((set) => ({
  activeTab: "incident",
  setActiveTab: (tab) => set({ activeTab: tab }),

  predictionRequest: {
    vessel_type: "소형어선",
    simulation_hours: 24,
    last_coordinate: { lon: 126.2, lat: 34.5 },
    last_seen_at: new Date().toISOString(),
  },
  setPredictionRequest: (req) =>
    set((s) => ({ predictionRequest: { ...s.predictionRequest, ...req } })),

  prediction: null,
  setPrediction: (p) => set({ prediction: p, selectedTimeStepHour: 0 }),

  briefing: null,
  setBriefing: (b) => set({ briefing: b }),

  selectedTimeStepHour: 0,
  setSelectedTimeStepHour: (h) => set({ selectedTimeStepHour: h }),

  isSubmitting: false,
  setIsSubmitting: (v) => set({ isSubmitting: v }),

  isBriefingLoading: false,
  setIsBriefingLoading: (v) => set({ isBriefingLoading: v }),

  mapPickMode: false,
  setMapPickMode: (v) => set({ mapPickMode: v }),
}));
