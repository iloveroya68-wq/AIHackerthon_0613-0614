"""Integration tests for SAR API endpoints."""

import json
import pytest


@pytest.mark.django_db
class TestPredictionCreate:
    def test_success_returns_201(self, api_client, vessel_payload):
        resp = api_client.post(
            "/api/v1/predictions/",
            data=json.dumps(vessel_payload),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["time_horizon_hours"] == 3
        assert data["search_zones"]["type"] == "FeatureCollection"
        assert len(data["search_zones"]["features"]) == 3
        assert isinstance(data["data_freshness_ok"], bool)

    def test_time_steps_present(self, api_client, vessel_payload):
        resp = api_client.post(
            "/api/v1/predictions/",
            data=json.dumps(vessel_payload),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "time_steps" in data
        assert len(data["time_steps"]) == vessel_payload["simulation_hours"]
        assert data["time_steps"][0]["hours"] == 1
        assert data["time_steps"][-1]["hours"] == vessel_payload["simulation_hours"]

    def test_priority_zones_ordered(self, api_client, vessel_payload):
        resp = api_client.post(
            "/api/v1/predictions/",
            data=json.dumps(vessel_payload),
            content_type="application/json",
        )
        features = resp.json()["search_zones"]["features"]
        priorities = [f["properties"]["priority"] for f in features]
        assert priorities == [1, 2, 3]

    def test_invalid_vessel_type_422(self, api_client, vessel_payload):
        vessel_payload["vessel_type"] = "잠수함"
        resp = api_client.post(
            "/api/v1/predictions/",
            data=json.dumps(vessel_payload),
            content_type="application/json",
        )
        assert resp.status_code == 422

    def test_missing_required_field_422(self, api_client):
        payload = {"last_seen_at": "2026-05-21T08:15:00+09:00", "vessel_type": "소형어선"}
        resp = api_client.post(
            "/api/v1/predictions/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 422

    def test_coordinates_outside_korean_waters_422(self, api_client, vessel_payload):
        vessel_payload["last_coordinate"] = {"lon": 10.0, "lat": 55.0}
        resp = api_client.post(
            "/api/v1/predictions/",
            data=json.dumps(vessel_payload),
            content_type="application/json",
        )
        assert resp.status_code in (400, 422)

    def test_deterministic_result(self, api_client, vessel_payload):
        resp1 = api_client.post(
            "/api/v1/predictions/",
            data=json.dumps(vessel_payload),
            content_type="application/json",
        )
        # Different request_id → different UUID, but same physics
        import copy
        p2 = copy.deepcopy(vessel_payload)
        resp2 = api_client.post(
            "/api/v1/predictions/",
            data=json.dumps(p2),
            content_type="application/json",
        )
        d1, d2 = resp1.json(), resp2.json()
        # Same drift vector from same input (seeded RNG)
        assert d1["drift_vector"]["direction_deg"] == d2["drift_vector"]["direction_deg"]
        assert d1["predicted_center"] == d2["predicted_center"]


@pytest.mark.django_db
class TestPredictionDetail:
    def test_get_existing(self, api_client, vessel_payload):
        create_resp = api_client.post(
            "/api/v1/predictions/",
            data=json.dumps(vessel_payload),
            content_type="application/json",
        )
        pid = create_resp.json()["request_id"]
        get_resp = api_client.get(f"/api/v1/predictions/{pid}/")
        assert get_resp.status_code == 200
        assert get_resp.json()["request_id"] == pid

    def test_get_nonexistent_404(self, api_client):
        resp = api_client.get("/api/v1/predictions/00000000-0000-0000-0000-000000000000/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestBriefing:
    def test_create_briefing(self, api_client, vessel_payload):
        pred = api_client.post(
            "/api/v1/predictions/",
            data=json.dumps(vessel_payload),
            content_type="application/json",
        ).json()
        brief_resp = api_client.post(f"/api/v1/predictions/{pred['request_id']}/briefing/")
        assert brief_resp.status_code == 201
        data = brief_resp.json()
        assert len(data["sections"]) == 4
        assert "지휘관" in data["disclaimer"]

    def test_briefing_idempotent(self, api_client, vessel_payload):
        pred = api_client.post(
            "/api/v1/predictions/",
            data=json.dumps(vessel_payload),
            content_type="application/json",
        ).json()
        r1 = api_client.post(f"/api/v1/predictions/{pred['request_id']}/briefing/")
        r2 = api_client.post(f"/api/v1/predictions/{pred['request_id']}/briefing/")
        assert r1.status_code == 201
        assert r2.status_code == 200
        assert r1.json()["request_id"] == r2.json()["request_id"]


@pytest.mark.django_db
class TestRiskForecast:
    def test_default_params(self, api_client):
        resp = api_client.get("/api/v1/risk/forecast/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_grid"]["type"] == "FeatureCollection"
        assert 0.0 <= data["dri_score"] <= 1.0

    def test_with_params(self, api_client):
        resp = api_client.get(
            "/api/v1/risk/forecast/",
            {
                "area_name": "연평도 인근 서해",
                "bbox": "124.1,37.6,124.9,38.3",
                "vessel_types": "소형어선,레저보트",
            },
        )
        assert resp.status_code == 200


@pytest.mark.django_db
def test_health(api_client):
    resp = api_client.get("/api/v1/health/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
