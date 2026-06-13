"""
MockEngine — deterministic, physics-plausible drift prediction.

Same (lon, lat, vessel_type) input → same output every time (seeded RNG).
Implements DriftEngineProtocol without importing real oceanographic models.
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from datetime import datetime, timezone
from typing import Any

from contracts.models import (
    Coordinate,
    DriftVector,
    EnginePredictionResult,
    GeoJSONFeatureCollection,
    PredictionRequest,
    TimeStepResult,
    VesselType,
)

# Leeway coefficients per vessel type (fraction of wind speed)
_LEEWAY: dict[VesselType, float] = {
    VesselType.SMALL_FISHING: 0.032,
    VesselType.STANDARD_FISHING: 0.025,
    VesselType.PERSON_WITH_LIFEJACKET: 0.015,
    VesselType.LIFE_RAFT: 0.0375,
    VesselType.LEISURE_BOAT: 0.045,
}

# Base radii (km) for 6-hour simulation at priorities 1/2/3
_BASE_RADII_KM = [3.0, 4.9, 7.7]
_CUMULATIVE_PROBS = [0.60, 0.80, 0.95]


class MockEngine:
    """Produces plausible EnginePredictionResult using seeded RNG + IAMSAR-style vectors."""

    # ------------------------------------------------------------------ public

    def predict(self, request: PredictionRequest) -> EnginePredictionResult:
        t0 = time.perf_counter()
        rng = _make_rng(request)

        # 실시간 환경 데이터 시도 → 실패 시 seeded RNG fallback
        if True:
            # seeded RNG fallback (발표/테스트 모드)
            current_dir = rng.uniform(20.0, 70.0)
            current_kt  = rng.uniform(0.5, 1.8)
            wind_dir    = rng.uniform(270.0, 330.0)
            wind_ms     = rng.uniform(5.0, 15.0)
            data_source_current = "KHOA-MOCK"
            data_source_weather = "KMA-MOCK"
            data_freshness_ok   = True

        leeway = _LEEWAY[request.vessel_type]
        wind_kt = wind_ms * 1.94384
        leeway_kt = wind_kt * leeway

        drift_dir, drift_kt = _combine_vectors(current_dir, current_kt, wind_dir, leeway_kt)

        # Build time_steps for each hour 1 → simulation_hours
        time_steps: list[TimeStepResult] = []
        for h in range(1, request.simulation_hours + 1):
            step = self._compute_step(request, rng, drift_dir, drift_kt, h, leeway, wind_ms)
            time_steps.append(step)

        # Main result = last step (= simulation_hours)
        main_step = time_steps[-1]

        # L3 correction
        similar_count = rng.randint(15, 50)
        l3_applied = similar_count >= 30
        dl_lat = rng.uniform(-0.004, 0.004) if l3_applied else 0.0
        dl_lon = rng.uniform(-0.004, 0.004) if l3_applied else 0.0

        fake_elapsed = round(time.perf_counter() - t0 + rng.uniform(0.5, 2.5), 2)

        return EnginePredictionResult(
            request_id=str(request.request_id),
            computed_at=datetime.now(tz=timezone.utc),
            elapsed_seconds=fake_elapsed,
            time_horizon_hours=request.simulation_hours,
            drift_vector=DriftVector(
                direction_deg=round(drift_dir % 360, 1),
                speed_knots=round(drift_kt, 3),
                current_speed_knots=round(current_kt, 2),
                current_direction_deg=round(current_dir, 1),
                wind_speed_ms=round(wind_ms, 1),
                wind_direction_deg=round(wind_dir, 1),
                leeway_coefficient=leeway,
            ),
            predicted_center=main_step.predicted_center,
            search_zones=main_step.search_zones,
            particle_count=1000,
            l3_correction_applied=l3_applied,
            l3_delta_lat=round(dl_lat, 6),
            l3_delta_lon=round(dl_lon, 6),
            similar_incidents_count=similar_count,
            weight_l1=0.30,
            weight_l2=0.50,
            weight_l3=0.20 if l3_applied else 0.0,
            current_data_source=data_source_current,
            weather_data_source=data_source_weather,
            data_freshness_ok=data_freshness_ok,
            time_steps=time_steps,
        )

    # --------------------------------------------------------------- internal

    def _compute_step(
        self,
        request: PredictionRequest,
        rng: random.Random,
        drift_dir: float,
        drift_kt: float,
        hours: int,
        leeway: float,
        wind_ms: float,
    ) -> TimeStepResult:
        distance_nm = drift_kt * hours
        distance_km = distance_nm * 1.852

        center_lon, center_lat = _move_point(
            request.last_coordinate.lon,
            request.last_coordinate.lat,
            drift_dir,
            distance_nm,
        )

        # Scale radii with sqrt(hours) — uncertainty grows with sqrt(time)
        scale = math.sqrt(hours / 6.0)
        radii_km = [r * scale * rng.uniform(0.92, 1.08) for r in _BASE_RADII_KM]
        zones = _create_search_zones(center_lon, center_lat, drift_dir, radii_km)

        return TimeStepResult(
            hours=hours,
            search_zones=zones,
            predicted_center=Coordinate(lon=round(center_lon, 6), lat=round(center_lat, 6)),
            drift_distance_nm=round(distance_nm, 3),
        )


# ---------------------------------------------------------------------------
# Pure math helpers
# ---------------------------------------------------------------------------

def _make_rng(request: PredictionRequest) -> random.Random:
    key = (
        f"{request.last_coordinate.lon:.4f}"
        f":{request.last_coordinate.lat:.4f}"
        f":{request.vessel_type.value}"
    )
    seed = int(hashlib.md5(key.encode()).hexdigest(), 16) % (2**31)
    return random.Random(seed)


def _combine_vectors(
    dir1_deg: float, spd1_kt: float,
    dir2_deg: float, spd2_kt: float,
) -> tuple[float, float]:
    """Vector sum of two (bearing, speed) pairs → (bearing, speed)."""
    r1, r2 = math.radians(dir1_deg), math.radians(dir2_deg)
    east = spd1_kt * math.sin(r1) + spd2_kt * math.sin(r2)
    north = spd1_kt * math.cos(r1) + spd2_kt * math.cos(r2)
    speed = math.hypot(east, north)
    bearing = math.degrees(math.atan2(east, north)) % 360
    return bearing, speed


def _move_point(lon: float, lat: float, bearing_deg: float, distance_nm: float) -> tuple[float, float]:
    """Move a geographic point by distance_nm nautical miles toward bearing_deg."""
    dist_km = distance_nm * 1.852
    lat_rad = math.radians(lat)
    b_rad = math.radians(bearing_deg)

    north_km = dist_km * math.cos(b_rad)
    east_km = dist_km * math.sin(b_rad)

    d_lat = north_km / 111.0
    d_lon = east_km / (111.0 * math.cos(lat_rad))
    return lon + d_lon, lat + d_lat


def _ellipse_polygon(
    center_lon: float,
    center_lat: float,
    a_km: float,   # semi-major axis (along drift)
    b_km: float,   # semi-minor axis (perpendicular to drift)
    drift_deg: float,
    n: int = 20,
) -> list[list[float]]:
    """
    Rotated ellipse as a GeoJSON polygon ring [[lon, lat], …].

    Coordinate frame:
      u = unit vector along drift  = (sin θ, cos θ)  in (east, north)
      v = unit vector 90° CCW      = (−cos θ, sin θ)

    At ellipse parameter φ:
      east_km  = a·cos φ·sin θ  +  b·sin φ·(−cos θ)
      north_km = a·cos φ·cos θ  +  b·sin φ·sin θ
    """
    lat_rad = math.radians(center_lat)
    lat_scale = 1.0 / 111.0           # km → °lat
    lon_scale = 1.0 / (111.0 * math.cos(lat_rad))  # km → °lon

    theta = math.radians(drift_deg)
    coords: list[list[float]] = []

    for i in range(n):
        phi = 2 * math.pi * i / n
        east_km = a_km * math.cos(phi) * math.sin(theta) + b_km * math.sin(phi) * (-math.cos(theta))
        north_km = a_km * math.cos(phi) * math.cos(theta) + b_km * math.sin(phi) * math.sin(theta)
        coords.append([
            round(center_lon + east_km * lon_scale, 6),
            round(center_lat + north_km * lat_scale, 6),
        ])

    coords.append(coords[0])  # close ring
    return coords


def _create_search_zones(
    center_lon: float,
    center_lat: float,
    drift_deg: float,
    radii_km: list[float],
) -> GeoJSONFeatureCollection:
    features: list[dict[str, Any]] = []
    for priority, (r, prob) in enumerate(zip(radii_km, _CUMULATIVE_PROBS), start=1):
        a_km = r * 1.35   # elongated along drift
        b_km = r * 0.85   # compressed perpendicular
        area = round(math.pi * a_km * b_km, 1)

        features.append({
            "type": "Feature",
            "properties": {
                "priority": priority,
                "cumulative_probability": prob,
                "area_km2": area,
                "center_lon": round(center_lon, 6),
                "center_lat": round(center_lat, 6),
                "radius_km": round(r, 2),
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [_ellipse_polygon(center_lon, center_lat, a_km, b_km, drift_deg)],
            },
        })

    return {"type": "FeatureCollection", "features": features}
