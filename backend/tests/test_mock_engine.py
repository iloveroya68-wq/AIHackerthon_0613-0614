"""Contract tests: MockEngine output must satisfy EnginePredictionResult schema."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent.parent  # DRIFT/


@pytest.fixture(scope="module")
def engine():
    import sys
    sys.path.insert(0, str(ROOT))
    from apps.sar.mock_engine import MockEngine
    return MockEngine()


@pytest.fixture(scope="module")
def sample_request():
    import sys
    sys.path.insert(0, str(ROOT))
    from contracts.models import PredictionRequest
    return PredictionRequest(
        last_coordinate={"lon": 124.372, "lat": 37.959},
        last_seen_at="2026-05-21T08:15:00+09:00",
        vessel_type="소형어선",
        simulation_hours=6,
    )


def test_output_validates_contract(engine, sample_request):
    from contracts.models import EnginePredictionResult
    result = engine.predict(sample_request)
    # Re-validate by round-tripping through the model
    dumped = result.model_dump(mode="json")
    re_parsed = EnginePredictionResult(**dumped)
    assert re_parsed.request_id == result.request_id


def test_search_zones_geojson(engine, sample_request):
    result = engine.predict(sample_request)
    zones = result.search_zones
    assert zones["type"] == "FeatureCollection"
    features = zones["features"]
    assert len(features) == 3
    priorities = sorted(f["properties"]["priority"] for f in features)
    assert priorities == [1, 2, 3]


def test_polygon_coordinates_lon_lat_order(engine, sample_request):
    result = engine.predict(sample_request)
    for feature in result.search_zones["features"]:
        ring = feature["geometry"]["coordinates"][0]
        for point in ring:
            lon, lat = point
            assert 100 <= lon <= 145, f"lon {lon} outside plausible range (GeoJSON should be [lon,lat])"
            assert 25 <= lat <= 45, f"lat {lat} outside plausible range"


def test_time_steps_count(engine, sample_request):
    result = engine.predict(sample_request)
    assert result.time_steps is not None
    assert len(result.time_steps) == sample_request.simulation_hours
    for i, step in enumerate(result.time_steps, start=1):
        assert step.hours == i


def test_drift_distance_grows_with_time(engine, sample_request):
    result = engine.predict(sample_request)
    distances = [s.drift_distance_nm for s in result.time_steps]
    for d_prev, d_next in zip(distances, distances[1:]):
        assert d_next > d_prev, "drift distance should increase with time"


def test_deterministic_output(engine, sample_request):
    r1 = engine.predict(sample_request)
    r2 = engine.predict(sample_request)
    assert r1.drift_vector.direction_deg == r2.drift_vector.direction_deg
    assert r1.predicted_center.lon == r2.predicted_center.lon


def test_different_vessel_types_give_different_results(engine, sample_request):
    from contracts.models import PredictionRequest
    req_leisure = PredictionRequest(
        last_coordinate={"lon": 124.372, "lat": 37.959},
        last_seen_at="2026-05-21T08:15:00+09:00",
        vessel_type="레저보트",
        simulation_hours=6,
    )
    r_small = engine.predict(sample_request)
    r_leisure = engine.predict(req_leisure)
    assert r_small.drift_vector.leeway_coefficient != r_leisure.drift_vector.leeway_coefficient


def test_output_satisfies_json_schema(engine, sample_request):
    import jsonschema

    schema_path = ROOT / "contracts" / "schemas" / "engine_prediction_result.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    result = engine.predict(sample_request)
    jsonschema.validate(instance=result.model_dump(mode="json"), schema=schema)
