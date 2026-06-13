"""
DRIFT data contracts — Pydantic v2 models.

All geographic data uses GeoJSON FeatureCollection.
Coordinate order is always [longitude, latitude] per GeoJSON spec (RFC 7946).

These models are the ONLY inter-module interface:
  engine  → produces EnginePredictionResult
  report  → produces BriefingResult
  risk    → produces RiskForecastResult
  backend → consumes all three, exposes REST API
  frontend→ consumes via openapi.yaml

DO NOT add business logic here. Pure data shapes only.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

class VesselType(str, Enum):
    """Vessel / object-in-water type. Controls Leeway coefficient in L1."""
    SMALL_FISHING = "소형어선"          # < 5 tons   | Leeway 3.0–3.5 %
    STANDARD_FISHING = "표준어선"       # 5–20 tons  | Leeway 2.0–3.0 %
    PERSON_WITH_LIFEJACKET = "구명조끼착용자"  # Leeway 1.5 %
    LIFE_RAFT = "구명뗏목"              # Leeway 3.5–4.0 %
    LEISURE_BOAT = "레저보트"           # Leeway 4.0–5.0 %


class Coordinate(BaseModel):
    """Geographic point. lon/lat order matches GeoJSON [lon, lat]."""
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude (decimal degrees)")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude (decimal degrees)")


class DriftVector(BaseModel):
    """Resultant drift direction and speed from L1 physics model."""
    direction_deg: float = Field(..., ge=0.0, lt=360.0, description="True bearing (°), 0 = North")
    speed_knots: float = Field(..., ge=0.0, description="Resultant drift speed (knots)")
    current_speed_knots: float = Field(..., ge=0.0)
    current_direction_deg: float = Field(..., ge=0.0, lt=360.0)
    wind_speed_ms: float = Field(..., ge=0.0)
    wind_direction_deg: float = Field(..., ge=0.0, lt=360.0)
    leeway_coefficient: float = Field(..., ge=0.0, le=0.10, description="Leeway fraction (e.g. 0.032)")


class SearchZoneProperties(BaseModel):
    """GeoJSON Feature properties for a single priority search polygon."""
    priority: int = Field(..., ge=1, le=3, description="1 = highest (60% contour)")
    cumulative_probability: float = Field(..., ge=0.0, le=1.0, description="e.g. 0.60 for priority-1")
    area_km2: float = Field(..., gt=0.0)
    center_lon: float
    center_lat: float
    radius_km: float = Field(..., gt=0.0, description="Approximate radius of the polygon")


# ---------------------------------------------------------------------------
# GeoJSON type alias — kept as dict so modules can use any GeoJSON library.
# Validation: must be {"type": "FeatureCollection", "features": [...]}
# ---------------------------------------------------------------------------

GeoJSONFeatureCollection = dict[str, Any]


def _validate_feature_collection(v: Any) -> GeoJSONFeatureCollection:
    if not isinstance(v, dict):
        raise ValueError("Must be a dict (GeoJSON FeatureCollection)")
    if v.get("type") != "FeatureCollection":
        raise ValueError('GeoJSON type must be "FeatureCollection"')
    if not isinstance(v.get("features"), list):
        raise ValueError('"features" must be a list')
    return v


# ---------------------------------------------------------------------------
# Contract 1 — PredictionRequest  (INPUT)
# ---------------------------------------------------------------------------

class PredictionRequest(BaseModel):
    """
    All information a field operator provides when a vessel goes missing.
    Three mandatory fields (last coordinate, time, vessel type) — everything
    else is optional to lower friction during emergencies.
    """

    request_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="UUID assigned at intake; echoed in all downstream results",
    )
    vessel_id: str | None = Field(
        None,
        description="V-Pass / AIS vessel ID if known",
        examples=["V-PASS-123456789"],
    )
    last_coordinate: Coordinate = Field(
        ...,
        description="Last confirmed GPS position [lon, lat]",
    )
    last_seen_at: datetime = Field(
        ...,
        description="UTC timestamp of the last confirmed signal",
    )
    vessel_type: VesselType
    tonnage_tons: float | None = Field(
        None,
        ge=0.0,
        description="Gross tonnage — used to select Leeway sub-range",
    )
    simulation_hours: int = Field(
        default=6,
        ge=1,
        le=24,
        description="How many hours ahead to simulate drift",
    )
    notes: str | None = Field(
        None,
        max_length=500,
        description="Free-text field notes from the operator",
    )

    model_config = {"json_schema_extra": {"title": "PredictionRequest"}}


# ---------------------------------------------------------------------------
# Contract 2 — EnginePredictionResult  (L1 + L2 + L3 OUTPUT → backend)
# ---------------------------------------------------------------------------

class TimeStepResult(BaseModel):
    """Pre-computed search zones for a single time step (used by frontend time slider)."""
    hours: int = Field(..., ge=1, le=24, description="Hours after last known position")
    search_zones: GeoJSONFeatureCollection
    predicted_center: Coordinate
    drift_distance_nm: float = Field(..., ge=0.0, description="Total drift distance in nautical miles")
    debug_particles: list[list[float]] | None = Field(
        default=None,
        description="Debug only: [[lon, lat], ...] of surviving particles (subsampled to ≤200)",
    )

    @field_validator("search_zones", mode="before")
    @classmethod
    def validate_search_zones(cls, v: Any) -> Any:
        return _validate_feature_collection(v)


class EnginePredictionResult(BaseModel):
    """
    Output of the drift engine package (L1 physics + L2 Monte Carlo + L3 ML).
    Backend consumes this; engine produces it. They share ONLY this contract.
    search_zones is a GeoJSON FeatureCollection with 3 priority polygons.
    Feature properties must conform to SearchZoneProperties.
    """

    request_id: str
    computed_at: datetime
    elapsed_seconds: float = Field(..., ge=0.0, description="Wall-clock engine runtime")

    time_horizon_hours: int = Field(..., ge=1, le=24)

    # --- L1: deterministic center ---
    drift_vector: DriftVector
    predicted_center: Coordinate = Field(
        ...,
        description="L1 deterministic endpoint before Monte Carlo spread",
    )

    # --- L2: probability zones ---
    # GeoJSON FeatureCollection; features[i].properties ~ SearchZoneProperties
    search_zones: GeoJSONFeatureCollection = Field(
        ...,
        description="GeoJSON FeatureCollection with 3 priority search polygons",
    )
    particle_count: int = Field(default=1000, ge=0, description="Monte Carlo particles surviving land mask")

    # --- L3: ML correction ---
    l3_correction_applied: bool = Field(
        ...,
        description="False when training data < 30 records (L3 weight = 0)",
    )
    l3_delta_lat: float = Field(default=0.0, description="ML latitude correction (°)")
    l3_delta_lon: float = Field(default=0.0, description="ML longitude correction (°)")
    similar_incidents_count: int = Field(
        default=0,
        ge=0,
        description="Number of historical incidents used for L3 training",
    )

    # --- Fusion weights (sum must equal 1.0) ---
    weight_l1: float = Field(default=0.0, ge=0.0, le=1.0)
    weight_l2: float = Field(default=1.0, ge=0.0, le=1.0)
    weight_l3: float = Field(default=0.0, ge=0.0, le=1.0)

    # --- Data provenance ---
    current_data_source: str = Field(default="KHOA", description="Tidal current API source")
    weather_data_source: str = Field(default="KMA", description="Meteorological API source")
    data_freshness_ok: bool = Field(
        ...,
        description="False when live API unavailable and CSV fallback was used",
    )

    # --- Pre-computed time steps for frontend slider (+1h, +2h, …) ---
    time_steps: list[TimeStepResult] | None = Field(
        default=None,
        description="Per-hour search zones for time slider; hours 1..simulation_hours",
    )

    @field_validator("search_zones", mode="before")
    @classmethod
    def validate_search_zones(cls, v: Any) -> Any:
        return _validate_feature_collection(v)

    model_config = {"json_schema_extra": {"title": "EnginePredictionResult"}}


# ---------------------------------------------------------------------------
# Contract 3 — BriefingResult  (L4 LLM OUTPUT → backend)
# ---------------------------------------------------------------------------

class BriefingSection(BaseModel):
    """One of the four standardised briefing sections."""
    section_id: int = Field(..., ge=1, le=4)
    title: str
    body: str = Field(..., description="Korean-language narrative paragraph")
    sources: list[str] = Field(default_factory=list, description="Layer tags: L1, L2, L3, L4")


class RagSourceItem(BaseModel):
    """A single document or incident record retrieved via RAG."""
    source_type: str = Field(..., description="'incident' or 'document'")
    source_id: str = Field(..., description="incident_id or chunk_id")
    summary: str = Field(..., description="One-line description of the reference")
    category: str | None = Field(None, description="Incident type or document category")


class BriefingResult(BaseModel):
    """
    L4 (GPT-4o) operational briefing generated from the EnginePredictionResult JSON.
    LLM must NOT invent numbers — body fields only rephrase values from engine output.
    disclaimer is mandatory and must reference '현장 지휘관'.
    """

    request_id: str
    generated_at: datetime
    elapsed_seconds: float = Field(..., ge=0.0)

    risk_score: int = Field(..., ge=0, le=100, description="Composite risk 0–100")
    confidence_label: str = Field(
        ...,
        description="Human-readable confidence: '높음' | '보통' | '낮음'",
    )

    sections: list[BriefingSection] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Exactly 4 sections: summary, history, rationale, contingency",
    )

    model_used: str = Field(default="gpt-4o", description="LLM model identifier")
    prompt_tokens: int | None = Field(None, ge=0)
    completion_tokens: int | None = Field(None, ge=0)

    pdf_url: str | None = Field(None, description="Signed URL to generated PDF report")
    rag_sources: list[RagSourceItem] = Field(
        default_factory=list,
        description="RAG-retrieved incidents and documents used to generate this briefing",
    )
    disclaimer: str = Field(
        ...,
        description="Must contain '최종 판단은 현장 지휘관'. Always displayed in UI.",
    )

    @field_validator("disclaimer")
    @classmethod
    def disclaimer_must_reference_commander(cls, v: str) -> str:
        if "지휘관" not in v:
            raise ValueError("disclaimer must reference '지휘관' per safety policy")
        return v

    model_config = {"json_schema_extra": {"title": "BriefingResult"}}


# ---------------------------------------------------------------------------
# Contract 4 — RiskForecastResult  (P1 OUTPUT → backend)
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    HIGH = "고위험"
    CAUTION = "주의"
    WATCH = "관찰"


class RiskCause(BaseModel):
    factor: str = Field(..., description="e.g. '조류 반전', '풍속 강화', '파고 상승'")
    description: str
    severity: RiskLevel


class RecommendedAction(BaseModel):
    priority: int = Field(..., ge=1)
    action: str
    target: str = Field(..., description="e.g. '순찰정 사전 배치', 'V-Pass 주의 알림'")


class RiskForecastResult(BaseModel):
    """
    P1 proactive risk heatmap for a given area + time window.
    risk_grid is a GeoJSON FeatureCollection of grid cells (Polygon features).
    Each feature's properties include 'risk_level' and 'dri_score'.
    Engine L3 model is reused for per-cell DRI scoring.
    """

    forecast_id: str = Field(default_factory=lambda: str(uuid4()))
    forecasted_at: datetime

    area_name: str = Field(..., description="e.g. '연평도 인근 서해'")
    bbox: list[float] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="[min_lon, min_lat, max_lon, max_lat]",
    )

    time_range_start: datetime
    time_range_end: datetime
    peak_risk_time: datetime

    vessel_types_targeted: list[VesselType] = Field(
        ...,
        min_length=1,
        description="Vessel types included in the forecast",
    )

    # GeoJSON FeatureCollection; each feature.properties has:
    #   risk_level: RiskLevel, dri_score: float [0,1]
    risk_grid: GeoJSONFeatureCollection = Field(
        ...,
        description="GeoJSON FeatureCollection of grid-cell polygons with DRI scores",
    )

    dri_score: float = Field(..., ge=0.0, le=1.0, description="Area-wide Drift Risk Index")
    dri_percentile: float = Field(..., ge=0.0, le=100.0, description="Relative to 90-day history")

    risk_causes: list[RiskCause] = Field(..., min_length=1)
    recommended_actions: list[RecommendedAction] = Field(..., min_length=1)

    max_wind_speed_ms: float = Field(..., ge=0.0)
    max_wave_height_m: float = Field(..., ge=0.0)
    max_current_speed_kt: float = Field(..., ge=0.0)
    tidal_reversal_time: datetime | None = Field(
        None,
        description="Next tidal reversal within the forecast window, if applicable",
    )

    vessels_at_risk_count: int = Field(..., ge=0, description="V-Pass vessels in high-risk zone")
    high_risk_area_km2: float = Field(..., ge=0.0)

    @field_validator("risk_grid", mode="before")
    @classmethod
    def validate_risk_grid(cls, v: Any) -> Any:
        return _validate_feature_collection(v)

    model_config = {"json_schema_extra": {"title": "RiskForecastResult"}}
