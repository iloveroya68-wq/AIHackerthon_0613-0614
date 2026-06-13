from __future__ import annotations

import math
import time
from datetime import UTC, datetime, timedelta

import numpy as np

from contracts.models import (
    Coordinate,
    DriftVector,
    EnginePredictionResult,
    PredictionRequest,
    TimeStepResult,
)

from .config import EngineConfig
from .data_sources import DataBundle, build_data_bundle
from .exceptions import DriftSimulationError
from .geo import local_offsets_m
from .l1_physics import calculate_l1
from .l2_monte_carlo import DriftSimulationResult, ParticleSnapshot, run_l2_step
from .l3_correction import predict_l3
from .search_zones import build_search_zones

EMPTY_SEARCH_ZONES = {"type": "FeatureCollection", "features": []}


class RealDriftEngine:
    def __init__(
        self,
        config: EngineConfig | None = None,
        data_bundle: DataBundle | None = None,
    ) -> None:
        self.config = config or EngineConfig.from_env()
        self.data_bundle = data_bundle or build_data_bundle(
            self.config.data_source, self.config.data_root
        )

    def predict(self, request: PredictionRequest) -> EnginePredictionResult:
        started = time.perf_counter()
        environment = self.data_bundle.environment.get_environment(
            request.last_coordinate.lat,
            request.last_coordinate.lon,
            request.last_seen_at,
        )
        leeway = self.data_bundle.leeway.coefficient(request.vessel_type)
        l1 = calculate_l1(request, environment, leeway)

        # Initial particle spread around starting point (deterministic)
        rng = np.random.default_rng(self.config.random_seed)
        count = self.config.particle_count
        angles = rng.uniform(0.0, 2.0 * math.pi, count)
        radii = self.config.seed_radius_m * np.sqrt(rng.uniform(0.0, 1.0, count))
        cos_lat = max(0.01, math.cos(math.radians(request.last_coordinate.lat)))
        seed_lons = request.last_coordinate.lon + (radii * np.sin(angles)) / (111_320.0 * cos_lat)
        seed_lats = request.last_coordinate.lat + (radii * np.cos(angles)) / 111_320.0

        # H:MM → H:00으로 내림. CSV/예보 데이터가 시간 단위이며,
        # H:00이 최종 신고 위치, H+1이 첫 번째 예측 영역이 되도록 정렬.
        last_utc = request.last_seen_at.astimezone(UTC)
        base_time = last_utc.replace(minute=0, second=0, microsecond=0, tzinfo=None)
        # L3 is called with simulation_hours=1 to match how training data was generated
        step_request = request.model_copy(update={"simulation_hours": 1})

        snapshots: list[ParticleSnapshot] = []
        l3_applied_any = False
        l3_delta_lon = l3_delta_lat = 0.0
        similar_incidents_count = 0
        stranded_hour: int | None = None

        for hour in range(1, request.simulation_hours + 1):
            step_time = base_time + timedelta(hours=hour - 1)

            # L2: 1-hour OpenDrift step from current particle positions
            try:
                snapshot = run_l2_step(seed_lons, seed_lats, step_time, environment, self.config, hour)
            except DriftSimulationError as exc:
                message = str(exc)
                if "stranded" in message or "no valid particles" in message:
                    # All particles stranded this step; expose an empty zone for this hour.
                    stranded_hour = hour
                    break
                raise

            # Land mask filtering — ray-cast if start positions available
            if snapshot.start_lon is not None:
                water_lon, water_lat = self.data_bundle.land_mask.filter_water_path(
                    snapshot.start_lon, snapshot.start_lat, snapshot.lon, snapshot.lat
                )
            else:
                water_lon, water_lat = self.data_bundle.land_mask.filter_water(
                    snapshot.lon, snapshot.lat
                )
            if len(water_lon) == 0:
                stranded_hour = hour
                break  # all particles on land — stop simulation here
            snapshot = ParticleSnapshot(hour, water_lon, water_lat)

            # L3: correct this step's particle cloud
            step_l2 = DriftSimulationResult([snapshot], len(snapshot.lon), "opendrift-leeway")
            l3 = predict_l3(step_request, environment, step_l2, leeway, self.config)

            if l3.applied:
                l3_applied_any = True
                l3_delta_lon = l3.delta_lon
                l3_delta_lat = l3.delta_lat
                similar_incidents_count = l3.similar_incidents_count
                shifted_lons = snapshot.lon + l3.delta_lon
                shifted_lats = snapshot.lat + l3.delta_lat
                # L3 shift can move particles onto land — re-filter
                wl, wla = self.data_bundle.land_mask.filter_water(shifted_lons, shifted_lats)
                seed_lons, seed_lats = (wl, wla) if len(wl) > 0 else (snapshot.lon, snapshot.lat)
                snapshots.append(ParticleSnapshot(hour, seed_lons.copy(), seed_lats.copy()))
            else:
                seed_lons = snapshot.lon.copy()
                seed_lats = snapshot.lat.copy()
                snapshots.append(snapshot)

        if not snapshots:
            if stranded_hour is None:
                raise RuntimeError("Iterative L2/L3 loop produced no snapshots")
            empty_center = Coordinate(
                lon=request.last_coordinate.lon,
                lat=request.last_coordinate.lat,
            )
            return EnginePredictionResult(
                request_id=str(request.request_id),
                computed_at=datetime.now(tz=UTC),
                elapsed_seconds=time.perf_counter() - started,
                time_horizon_hours=request.simulation_hours,
                drift_vector=DriftVector(
                    direction_deg=round(l1.direction_deg, 3),
                    speed_knots=round(l1.speed_knots, 4),
                    current_speed_knots=environment.current.speed_knots,
                    current_direction_deg=environment.current.direction_deg,
                    wind_speed_ms=environment.weather.wind_speed_ms,
                    wind_direction_deg=environment.weather.wind_direction_deg,
                    leeway_coefficient=l1.leeway_coefficient,
                ),
                predicted_center=empty_center,
                search_zones=EMPTY_SEARCH_ZONES,
                particle_count=0,
                l3_correction_applied=False,
                l3_delta_lat=0.0,
                l3_delta_lon=0.0,
                similar_incidents_count=0,
                weight_l1=0.0,
                weight_l2=1.0,
                weight_l3=0.0,
                current_data_source=environment.current.source,
                weather_data_source=environment.weather.source,
                data_freshness_ok=environment.data_freshness_ok,
                time_steps=[TimeStepResult(
                    hours=stranded_hour,
                    search_zones=EMPTY_SEARCH_ZONES,
                    predicted_center=empty_center,
                    drift_distance_nm=0.0,
                    debug_particles=[],
                )],
            )

        l2 = DriftSimulationResult(snapshots, len(snapshots[-1].lon), "opendrift-leeway-l3loop")

        # L3 is embedded in particle positions; search zones use corrected L2 only.
        w_l1, w_l2 = 0.0, 1.0

        time_steps: list[TimeStepResult] = []
        final_zones = None
        final_center = None
        final_distance_nm = 0.0
        for snapshot in l2.snapshots:
            l2_center_lon = float(snapshot.lon.mean())
            l2_center_lat = float(snapshot.lat.mean())
            fused_lon = l2_center_lon
            fused_lat = l2_center_lat
            fused_particles_lon = snapshot.lon + (fused_lon - l2_center_lon)
            fused_particles_lat = snapshot.lat + (fused_lat - l2_center_lat)
            # Fusion shift can push particles onto land; if too many lost, fall back to
            # snapshot (water-only) positions so zones are never built on land.
            wf_lon, wf_lat = self.data_bundle.land_mask.filter_water(fused_particles_lon, fused_particles_lat)
            if len(wf_lon) > 0:
                fused_particles_lon, fused_particles_lat = wf_lon, wf_lat
            else:
                fused_particles_lon, fused_particles_lat = snapshot.lon.copy(), snapshot.lat.copy()
            zones, center_lon, center_lat = build_search_zones(
                fused_particles_lon, fused_particles_lat
            )
            zones = self.data_bundle.land_mask.clip_feature_collection(zones)
            east, north = local_offsets_m(
                [center_lon], [center_lat],
                request.last_coordinate.lon, request.last_coordinate.lat,
            )
            distance_nm = math.hypot(float(east[0]), float(north[0])) / 1852.0
            final_zones = zones
            final_center = Coordinate(lon=center_lon, lat=center_lat)
            final_distance_nm = round(distance_nm, 3)
            debug_pts = [[round(float(fused_particles_lon[i]), 5), round(float(fused_particles_lat[i]), 5)] for i in range(len(fused_particles_lon))]
            time_steps.append(TimeStepResult(
                hours=snapshot.hours,
                search_zones=zones,
                predicted_center=final_center,
                drift_distance_nm=final_distance_nm,
                debug_particles=debug_pts,
            ))

        if final_zones is None or final_center is None:
            raise RuntimeError("No time steps produced")

        if stranded_hour is not None:
            final_zones = EMPTY_SEARCH_ZONES
            time_steps.append(TimeStepResult(
                hours=stranded_hour,
                search_zones=EMPTY_SEARCH_ZONES,
                predicted_center=final_center,
                drift_distance_nm=final_distance_nm,
                debug_particles=[],
            ))

        return EnginePredictionResult(
            request_id=str(request.request_id),
            computed_at=datetime.now(tz=UTC),
            elapsed_seconds=time.perf_counter() - started,
            time_horizon_hours=request.simulation_hours,
            drift_vector=DriftVector(
                direction_deg=round(l1.direction_deg, 3),
                speed_knots=round(l1.speed_knots, 4),
                current_speed_knots=environment.current.speed_knots,
                current_direction_deg=environment.current.direction_deg,
                wind_speed_ms=environment.weather.wind_speed_ms,
                wind_direction_deg=environment.weather.wind_direction_deg,
                leeway_coefficient=l1.leeway_coefficient,
            ),
            predicted_center=final_center,
            search_zones=final_zones,
            particle_count=0 if stranded_hour is not None else l2.particle_count,
            l3_correction_applied=l3_applied_any,
            l3_delta_lat=round(l3_delta_lat, 8),
            l3_delta_lon=round(l3_delta_lon, 8),
            similar_incidents_count=similar_incidents_count,
            weight_l1=w_l1,
            weight_l2=w_l2,
            weight_l3=0.0,
            current_data_source=environment.current.source,
            weather_data_source=environment.weather.source,
            data_freshness_ok=environment.data_freshness_ok,
            time_steps=time_steps,
        )
