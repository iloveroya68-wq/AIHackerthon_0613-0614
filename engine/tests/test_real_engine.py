from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
import pytest
from contracts.models import EnginePredictionResult, PredictionRequest, VesselType
from drift_engine.config import EngineConfig
from drift_engine.data_sources import (
    CurrentData,
    DataBundle,
    EnvironmentData,
    LandMask,
    LeewayCatalog,
    WeatherData,
)
from drift_engine.engine import RealDriftEngine
from drift_engine.exceptions import DriftSimulationError
from drift_engine.features import FEATURE_NAMES
from drift_engine.l1_physics import calculate_l1
from drift_engine.l2_monte_carlo import ParticleSnapshot
from drift_engine.search_zones import build_search_zones


@pytest.fixture
def environment() -> EnvironmentData:
    return EnvironmentData(
        weather=WeatherData(8.0, 315.0, source="TEST-KMA"),
        current=CurrentData(0.8, 45.0, source="TEST-KHOA"),
    )


@pytest.fixture
def prediction_request() -> PredictionRequest:
    return PredictionRequest(
        request_id="test-real-engine",
        last_coordinate={"lon": 126.375, "lat": 34.779},
        last_seen_at=datetime(2026, 6, 11, 9, tzinfo=UTC),
        vessel_type=VesselType.SMALL_FISHING,
        tonnage_tons=4.0,
        simulation_hours=3,
    )


@pytest.fixture
def data_bundle(environment) -> DataBundle:
    class StaticEnvironmentProvider:
        def get_environment(self, *_args):
            return environment

    return DataBundle(StaticEnvironmentProvider(), LeewayCatalog(), LandMask())


def _fake_l2_step(seed_lons, seed_lats, _step_time, _environment, _config, hour):
    offset = hour * 0.001
    return ParticleSnapshot(
        hour,
        np.asarray(seed_lons) + offset,
        np.asarray(seed_lats) + offset,
        start_lon=np.asarray(seed_lons),
        start_lat=np.asarray(seed_lats),
    )


def test_l1_produces_valid_motion(prediction_request, environment):
    result = calculate_l1(prediction_request, environment)
    assert 0 <= result.direction_deg < 360
    assert result.speed_knots > 0
    assert result.predicted_lon != prediction_request.last_coordinate.lon
    assert result.predicted_lat != prediction_request.last_coordinate.lat


def test_real_engine_returns_contract(monkeypatch, prediction_request, data_bundle):
    monkeypatch.setattr("drift_engine.engine.run_l2_step", _fake_l2_step)
    engine = RealDriftEngine(EngineConfig(
        particle_count=200,
        seed_radius_m=100.0,
        random_seed=7,
        l2_engine="opendrift",
    ), data_bundle=data_bundle)
    result = engine.predict(prediction_request)
    reparsed = EnginePredictionResult.model_validate(result.model_dump())

    assert len(reparsed.time_steps or []) == prediction_request.simulation_hours
    assert reparsed.particle_count == 200
    assert reparsed.l3_correction_applied is False
    assert math.isclose(reparsed.weight_l1 + reparsed.weight_l2 + reparsed.weight_l3, 1.0)
    assert reparsed.weight_l1 == 0.0
    assert reparsed.weight_l2 == 1.0
    assert reparsed.predicted_center == reparsed.time_steps[-1].predicted_center
    assert reparsed.search_zones == reparsed.time_steps[-1].search_zones


def test_search_zone_areas_increase(monkeypatch, prediction_request, data_bundle):
    monkeypatch.setattr("drift_engine.engine.run_l2_step", _fake_l2_step)
    result = RealDriftEngine(EngineConfig(
        particle_count=200,
        random_seed=9,
        l2_engine="opendrift",
    ), data_bundle=data_bundle).predict(prediction_request)
    areas = [feature["properties"]["area_km2"] for feature in result.search_zones["features"]]
    assert areas == sorted(areas)
    assert [f["properties"]["cumulative_probability"] for f in result.search_zones["features"]] == [
        0.60, 0.80, 0.95
    ]


def test_search_zones_support_sparse_particles():
    zones, center_lon, center_lat = build_search_zones(
        np.asarray([126.1]),
        np.asarray([34.2]),
    )

    assert center_lon == pytest.approx(126.1)
    assert center_lat == pytest.approx(34.2)
    assert len(zones["features"]) == 3


def test_l2_loop_is_reproducible(monkeypatch, prediction_request, data_bundle):
    monkeypatch.setattr("drift_engine.engine.run_l2_step", _fake_l2_step)
    config = EngineConfig(particle_count=200, random_seed=11, l2_engine="opendrift")
    first = RealDriftEngine(config, data_bundle=data_bundle).predict(prediction_request)
    second = RealDriftEngine(config, data_bundle=data_bundle).predict(prediction_request)
    assert first.predicted_center == second.predicted_center
    assert first.search_zones == second.search_zones


def test_engine_stops_at_last_surviving_particle_step(monkeypatch, prediction_request, data_bundle):
    def fake_l2_step(seed_lons, seed_lats, _step_time, _environment, _config, hour):
        if hour == 1:
            return ParticleSnapshot(
                hour,
                np.asarray([126.0, 126.001]),
                np.asarray([34.0, 34.001]),
                start_lon=np.asarray([126.0, 126.001]),
                start_lat=np.asarray([34.0, 34.001]),
            )
        raise DriftSimulationError("all particles stranded")

    monkeypatch.setattr("drift_engine.engine.run_l2_step", fake_l2_step)

    result = RealDriftEngine(
        EngineConfig(particle_count=2, random_seed=15, l2_engine="opendrift"),
        data_bundle=data_bundle,
    ).predict(prediction_request)

    assert result.time_horizon_hours == prediction_request.simulation_hours
    assert [step.hours for step in result.time_steps or []] == [1, 2]
    assert (result.time_steps or [])[-1].search_zones["features"] == []
    assert result.search_zones["features"] == []
    assert result.particle_count == 0


def test_l3_artifact_is_applied(monkeypatch, tmp_path, prediction_request, data_bundle):
    class FakeModel:
        def __init__(self, value):
            self.value = value

        def predict(self, _features):
            return [self.value]

    model_path = tmp_path / "model.joblib"
    metadata_path = tmp_path / "metadata.json"
    model_path.write_bytes(b"test-placeholder")
    metadata_path.write_text(json.dumps({
        "features": FEATURE_NAMES,
        "training_records": 100,
        "similar_incidents_count": 40,
    }), encoding="utf-8")
    artifact = {"east_model": FakeModel(120.0), "north_model": FakeModel(-80.0)}
    monkeypatch.setitem(sys.modules, "joblib", SimpleNamespace(load=lambda _path: artifact))
    monkeypatch.setattr("drift_engine.engine.run_l2_step", _fake_l2_step)

    result = RealDriftEngine(EngineConfig(
        particle_count=200,
        random_seed=13,
        l2_engine="opendrift",
        model_path=model_path,
        model_metadata_path=metadata_path,
    ), data_bundle=data_bundle).predict(prediction_request)

    assert result.l3_correction_applied is True
    assert result.similar_incidents_count == 40
    assert result.l3_delta_lon != 0
    assert result.l3_delta_lat != 0
    assert result.weight_l1 == 0.0
    assert result.weight_l2 == 1.0
    assert result.weight_l3 == 0.0
