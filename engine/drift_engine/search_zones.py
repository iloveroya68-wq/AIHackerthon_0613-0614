from __future__ import annotations

import math

import numpy as np

from .geo import local_offsets_m, move_point

PROBABILITIES = (0.60, 0.80, 0.95)


def _ellipse_ring(
    center_lon: float,
    center_lat: float,
    covariance: np.ndarray,
    probability: float,
    points: int = 48,
) -> tuple[list[list[float]], float, float]:
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    eigenvalues = np.maximum(eigenvalues, 25.0)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]
    scale = math.sqrt(-2.0 * math.log(1.0 - probability))
    axes = np.sqrt(eigenvalues) * scale
    ring: list[list[float]] = []
    for angle in np.linspace(0.0, 2.0 * math.pi, points, endpoint=False):
        local = eigenvectors @ np.asarray([axes[0] * math.cos(angle), axes[1] * math.sin(angle)])
        lon, lat = move_point(center_lon, center_lat, float(local[0]), float(local[1]))
        ring.append([round(lon, 6), round(lat, 6)])
    ring.append(ring[0])
    area_km2 = math.pi * axes[0] * axes[1] / 1_000_000.0
    radius_km = math.sqrt(axes[0] * axes[1]) / 1000.0
    return ring, area_km2, radius_km


def build_search_zones(lons: np.ndarray, lats: np.ndarray) -> tuple[dict, float, float]:
    valid = np.isfinite(lons) & np.isfinite(lats)
    if np.count_nonzero(valid) < 1:
        raise ValueError("At least one valid particle is required")
    lons = lons[valid]
    lats = lats[valid]
    center_lon = float(np.mean(lons))
    center_lat = float(np.mean(lats))
    east, north = local_offsets_m(lons, lats, center_lon, center_lat)
    if len(lons) == 1:
        covariance = np.diag([25.0, 25.0])
    else:
        covariance = np.cov(np.vstack([east, north]))
        covariance = np.asarray(covariance, dtype=float)
        if covariance.shape != (2, 2) or not np.all(np.isfinite(covariance)):
            covariance = np.diag([25.0, 25.0])
    features = []
    for priority, probability in enumerate(PROBABILITIES, start=1):
        ring, area, radius = _ellipse_ring(center_lon, center_lat, covariance, probability)
        features.append({
            "type": "Feature",
            "properties": {
                "priority": priority,
                "cumulative_probability": probability,
                "area_km2": round(area, 3),
                "center_lon": round(center_lon, 6),
                "center_lat": round(center_lat, 6),
                "radius_km": round(radius, 3),
            },
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        })
    return {"type": "FeatureCollection", "features": features}, center_lon, center_lat
