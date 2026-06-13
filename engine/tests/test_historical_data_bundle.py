from __future__ import annotations

import math
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from contracts.models import PredictionRequest, VesselType
from drift_engine.config import EngineConfig
from drift_engine.data_sources import build_data_bundle
from drift_engine.engine import RealDriftEngine


def _data_root() -> Path:
    value = os.environ.get("DRIFT_TEST_DATA_ROOT")
    if not value:
        pytest.skip("DRIFT_TEST_DATA_ROOT is not configured")
    root = Path(value)
    if not root.exists():
        pytest.skip(f"historical data bundle is unavailable: {root}")
    return root


def _request() -> PredictionRequest:
    return PredictionRequest(
        request_id="historical-bundle-test",
        last_coordinate={"lon": 126.2, "lat": 34.5},
        last_seen_at=datetime(2023, 9, 23, 12, tzinfo=ZoneInfo("Asia/Seoul")),
        vessel_type=VesselType.SMALL_FISHING,
        tonnage_tons=4.0,
        simulation_hours=1,
    )


def test_historical_provider_reads_cmems_and_khoa() -> None:
    bundle = build_data_bundle("historical", _data_root())
    request = _request()
    environment = bundle.environment.get_environment(
        request.last_coordinate.lat,
        request.last_coordinate.lon,
        request.last_seen_at,
    )

    assert environment.current.source.startswith("CMEMS:")
    assert environment.weather.source.startswith("KHOA-HISTORY:")
    assert math.isfinite(environment.current.eastward_mps or math.nan)
    assert math.isfinite(environment.current.northward_mps or math.nan)
    assert environment.weather.wind_speed_ms >= 0
    assert bundle.leeway.coefficient(VesselType.SMALL_FISHING) == pytest.approx(0.032)
    assert bundle.land_mask.available


def test_real_engine_runs_from_historical_bundle() -> None:
    bundle = build_data_bundle("historical", _data_root())
    result = RealDriftEngine(
        EngineConfig(particle_count=100, random_seed=17, l2_engine="synthetic"),
        data_bundle=bundle,
    ).predict(_request())

    assert result.current_data_source.startswith("CMEMS:")
    assert result.weather_data_source.startswith("KHOA-HISTORY:")
    assert result.particle_count == 100
    assert len(result.time_steps or []) == 1
    assert len(result.search_zones["features"]) == 3
