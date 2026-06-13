from __future__ import annotations

import math

EARTH_KM_PER_DEG_LAT = 111.32


def bearing_components(speed: float, direction_deg: float) -> tuple[float, float]:
    """Return east/north components for a bearing where 0 degrees is north."""
    angle = math.radians(direction_deg)
    return speed * math.sin(angle), speed * math.cos(angle)


def components_bearing(east: float, north: float) -> tuple[float, float]:
    return math.degrees(math.atan2(east, north)) % 360.0, math.hypot(east, north)


def move_point(lon: float, lat: float, east_m: float, north_m: float) -> tuple[float, float]:
    d_lat = north_m / (EARTH_KM_PER_DEG_LAT * 1000.0)
    cos_lat = max(0.01, math.cos(math.radians(lat)))
    d_lon = east_m / (EARTH_KM_PER_DEG_LAT * 1000.0 * cos_lat)
    return lon + d_lon, lat + d_lat


def local_offsets_m(
    lons: object, lats: object, origin_lon: float, origin_lat: float
) -> tuple[object, object]:
    import numpy as np

    cos_lat = max(0.01, math.cos(math.radians(origin_lat)))
    east = (np.asarray(lons) - origin_lon) * EARTH_KM_PER_DEG_LAT * 1000.0 * cos_lat
    north = (np.asarray(lats) - origin_lat) * EARTH_KM_PER_DEG_LAT * 1000.0
    return east, north
