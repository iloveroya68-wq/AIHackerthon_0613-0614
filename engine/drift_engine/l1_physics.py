from __future__ import annotations

from dataclasses import dataclass

from contracts.models import PredictionRequest

from .geo import bearing_components, components_bearing, move_point


@dataclass(frozen=True)
class L1Result:
    direction_deg: float
    speed_knots: float
    predicted_lon: float
    predicted_lat: float
    leeway_coefficient: float


def calculate_l1(
    request: PredictionRequest,
    environment: object,
    leeway_coefficient: float = 0.032,
) -> L1Result:
    leeway = leeway_coefficient
    current_east, current_north = bearing_components(
        environment.current.speed_knots, environment.current.direction_deg
    )
    wind_knots = environment.weather.wind_speed_ms * 1.94384 * leeway
    wind_east, wind_north = bearing_components(
        wind_knots, environment.weather.wind_direction_deg
    )
    east_knots = current_east + wind_east
    north_knots = current_north + wind_north
    direction, speed = components_bearing(east_knots, north_knots)
    seconds = request.simulation_hours * 3600.0
    lon, lat = move_point(
        request.last_coordinate.lon,
        request.last_coordinate.lat,
        east_knots * 0.514444 * seconds,
        north_knots * 0.514444 * seconds,
    )
    return L1Result(direction, speed, lon, lat, leeway)
