from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

from .config import EngineConfig
from .exceptions import DriftSimulationError
from .geo import bearing_components


@dataclass
class ParticleSnapshot:
    hours: int
    lon: np.ndarray
    lat: np.ndarray
    start_lon: np.ndarray | None = None
    start_lat: np.ndarray | None = None


@dataclass(frozen=True)
class DriftSimulationResult:
    snapshots: list[ParticleSnapshot]
    particle_count: int
    engine_name: str


def _forcing(environment: object) -> tuple[float, float, float, float]:
    if (
        environment.current.eastward_mps is not None
        and environment.current.northward_mps is not None
    ):
        current_x = environment.current.eastward_mps
        current_y = environment.current.northward_mps
    else:
        current_ms = environment.current.speed_knots * 0.514444
        current_x, current_y = bearing_components(current_ms, environment.current.direction_deg)
    wind_x, wind_y = bearing_components(
        environment.weather.wind_speed_ms, environment.weather.wind_direction_deg
    )
    return wind_x, wind_y, current_x, current_y


def _normalize_time_first(values: Any, dims: tuple[str, ...]) -> np.ndarray:
    array = np.asarray(values)
    if "time" in dims and dims[0] != "time":
        array = np.moveaxis(array, dims.index("time"), 0)
    return array


def run_l2_step(
    seed_lons: np.ndarray,
    seed_lats: np.ndarray,
    step_time: datetime,
    environment: object,
    config: EngineConfig,
    hour: int,
) -> ParticleSnapshot:
    """Run OpenDrift Leeway for exactly 1 hour from given particle positions.

    seed_lons/seed_lats: particle position arrays (no additional spread applied).
    For the first step, caller should pre-spread around the starting point.
    """
    try:
        from opendrift.models.leeway import Leeway
    except ImportError as exc:
        raise DriftSimulationError("OpenDrift is not installed") from exc

    wind_x, wind_y, current_x, current_y = _forcing(environment)
    model = Leeway(loglevel=50)
    model.set_config("environment:fallback:x_wind", wind_x)
    model.set_config("environment:fallback:y_wind", wind_y)
    model.set_config("environment:fallback:x_sea_water_velocity", current_x)
    model.set_config("environment:fallback:y_sea_water_velocity", current_y)
    model.set_config("environment:fallback:land_binary_mask", 0)
    model.set_config("general:use_auto_landmask", True)
    model.seed_elements(
        lon=seed_lons,
        lat=seed_lats,
        radius=0,
        time=step_time,
        object_type=1,
    )
    try:
        model.run(duration=timedelta(hours=1), time_step=900, time_step_output=3600)
    except ValueError as exc:
        message = str(exc)
        if (
            "No more active or scheduled elements" in message
            or "Simulation stopped within first timestep" in message
        ):
            raise DriftSimulationError(
                f"OpenDrift step {hour}h: all particles stranded"
            ) from exc
        raise
    lon_data = _normalize_time_first(model.result["lon"].values, model.result["lon"].dims)
    lat_data = _normalize_time_first(model.result["lat"].values, model.result["lat"].dims)
    if lon_data.shape[0] < 2:
        # All particles stranded before first output (auto_landmask active)
        raise DriftSimulationError(f"OpenDrift step {hour}h: all particles stranded within first sub-step")
    valid = np.isfinite(lon_data[-1]) & np.isfinite(lat_data[-1])
    if not np.any(valid):
        raise DriftSimulationError(f"OpenDrift step {hour}h: no valid particles remain")
    return ParticleSnapshot(hour, lon_data[-1][valid], lat_data[-1][valid],
                            start_lon=seed_lons[valid], start_lat=seed_lats[valid])
