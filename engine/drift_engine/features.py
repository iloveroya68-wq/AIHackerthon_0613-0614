from __future__ import annotations

import math

import numpy as np

FEATURE_NAMES = [
    "start_lat", "start_lon", "prediction_hours", "vessel_type_code", "tonnage_tons",
    "current_speed_knots", "current_dir_sin", "current_dir_cos",
    "wind_speed_ms", "wind_dir_sin", "wind_dir_cos", "leeway_coefficient",
    "l2_center_lat", "l2_center_lon", "l2_spread_km", "l2_east_std_km",
    "l2_north_std_km", "l2_major_axis_km", "l2_minor_axis_km",
    "l2_orientation_sin", "l2_orientation_cos", "particle_count",
    "month_sin", "month_cos", "hour_sin", "hour_cos",
]


def _cyclic(value: float, period: float) -> tuple[float, float]:
    angle = 2.0 * math.pi * value / period
    return math.sin(angle), math.cos(angle)


def build_features(
    request: object,
    environment: object,
    l2: object,
    leeway_coefficient: float,
) -> np.ndarray:
    final = l2.snapshots[-1]
    center_lon = float(np.mean(final.lon))
    center_lat = float(np.mean(final.lat))
    east_km = (final.lon - center_lon) * 111.32 * math.cos(math.radians(center_lat))
    north_km = (final.lat - center_lat) * 111.32
    spread_km = float(np.sqrt(np.mean(east_km**2 + north_km**2)))
    east_std_km = float(np.std(east_km))
    north_std_km = float(np.std(north_km))
    if len(east_km) >= 2:
        covariance = np.cov(np.vstack([east_km, north_km]))
        covariance = np.asarray(covariance, dtype=float)
    else:
        covariance = np.zeros((2, 2), dtype=float)
    if covariance.shape == (2, 2) and np.all(np.isfinite(covariance)):
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        order = np.argsort(eigenvalues)[::-1]
        eigenvalues = np.maximum(eigenvalues[order], 0.0)
        major_axis_km = float(np.sqrt(eigenvalues[0]))
        minor_axis_km = float(np.sqrt(eigenvalues[1]))
        principal = eigenvectors[:, order[0]]
        orientation_deg = math.degrees(math.atan2(float(principal[0]), float(principal[1]))) % 360.0
    else:
        major_axis_km = minor_axis_km = orientation_deg = 0.0
    current_sin, current_cos = _cyclic(environment.current.direction_deg, 360.0)
    wind_sin, wind_cos = _cyclic(environment.weather.wind_direction_deg, 360.0)
    orientation_sin, orientation_cos = _cyclic(orientation_deg, 360.0)
    month_sin, month_cos = _cyclic(request.last_seen_at.month - 1, 12.0)
    hour_sin, hour_cos = _cyclic(request.last_seen_at.hour, 24.0)
    vessel_types = list(type(request.vessel_type))
    vessel_type_code = float(vessel_types.index(request.vessel_type))
    return np.asarray([[
        request.last_coordinate.lat, request.last_coordinate.lon, request.simulation_hours,
        vessel_type_code, request.tonnage_tons or 0.0, environment.current.speed_knots, current_sin,
        current_cos, environment.weather.wind_speed_ms, wind_sin, wind_cos,
        leeway_coefficient, center_lat, center_lon, spread_km, east_std_km,
        north_std_km, major_axis_km, minor_axis_km, orientation_sin,
        orientation_cos, l2.particle_count, month_sin, month_cos, hour_sin,
        hour_cos,
    ]], dtype=float)
