// AUTO-GENERATED from contracts/schemas/*.json — do not edit manually
// Run: node scripts/gen-types.mjs to regenerate

export type VesselType =
  | "소형어선"
  | "표준어선"
  | "구명조끼착용자"
  | "구명뗏목"
  | "레저보트";

export type RiskLevel = "고위험" | "주의" | "관찰";

export interface Coordinate {
  lon: number;
  lat: number;
}

export interface PredictionRequest {
  request_id?: string;
  vessel_id?: string | null;
  last_coordinate: Coordinate;
  last_seen_at: string;
  vessel_type: VesselType;
  tonnage_tons?: number | null;
  simulation_hours?: number;
  notes?: string | null;
}

export interface DriftVector {
  direction_deg: number;
  speed_knots: number;
  current_speed_knots: number;
  current_direction_deg: number;
  wind_speed_ms: number;
  wind_direction_deg: number;
  leeway_coefficient: number;
}

export interface SearchZoneProperties {
  priority: 1 | 2 | 3;
  cumulative_probability: number;
  area_km2: number;
  center_lon: number;
  center_lat: number;
  radius_km: number;
}

export interface GeoJSONPolygon {
  type: "Polygon";
  coordinates: number[][][];
}

export interface GeoJSONFeature<P = Record<string, unknown>> {
  type: "Feature";
  properties: P;
  geometry: GeoJSONPolygon;
}

export interface GeoJSONFeatureCollection<P = Record<string, unknown>> {
  type: "FeatureCollection";
  features: GeoJSONFeature<P>[];
}

export type SearchZoneCollection = GeoJSONFeatureCollection<SearchZoneProperties>;

export interface TimeStepResult {
  hours: number;
  search_zones: GeoJSONFeatureCollection<SearchZoneProperties>;
  predicted_center: Coordinate;
  drift_distance_nm: number;
  debug_particles?: [number, number][] | null;
}

export interface EnginePredictionResult {
  request_id: string;
  computed_at: string;
  elapsed_seconds: number;
  time_horizon_hours: number;
  drift_vector: DriftVector;
  predicted_center: Coordinate;
  search_zones: GeoJSONFeatureCollection<SearchZoneProperties>;
  particle_count?: number;
  l3_correction_applied: boolean;
  l3_delta_lat?: number;
  l3_delta_lon?: number;
  similar_incidents_count?: number;
  weight_l1?: number;
  weight_l2?: number;
  weight_l3?: number;
  current_data_source?: string;
  weather_data_source?: string;
  data_freshness_ok: boolean;
  time_steps?: TimeStepResult[] | null;
}

export interface BriefingSection {
  section_id: 1 | 2 | 3 | 4;
  title: string;
  body: string;
  sources?: string[];
}

export interface BriefingResult {
  request_id: string;
  generated_at: string;
  elapsed_seconds: number;
  risk_score: number;
  confidence_label: string;
  sections: BriefingSection[];
  model_used?: string;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  pdf_url?: string | null;
  disclaimer: string;
}

export interface RiskCause {
  factor: string;
  description: string;
  severity: RiskLevel;
}

export interface RecommendedAction {
  priority: number;
  action: string;
  target: string;
}

export interface RiskGridCellProperties {
  risk_level: RiskLevel;
  dri_score: number;
}

export interface RiskForecastResult {
  forecast_id?: string;
  forecasted_at: string;
  area_name: string;
  bbox: [number, number, number, number];
  time_range_start: string;
  time_range_end: string;
  peak_risk_time: string;
  vessel_types_targeted: VesselType[];
  risk_grid: GeoJSONFeatureCollection<RiskGridCellProperties>;
  dri_score: number;
  dri_percentile: number;
  risk_causes: RiskCause[];
  recommended_actions: RecommendedAction[];
  max_wind_speed_ms: number;
  max_wave_height_m: number;
  max_current_speed_kt: number;
  tidal_reversal_time?: string | null;
  vessels_at_risk_count: number;
  high_risk_area_km2: number;
}
