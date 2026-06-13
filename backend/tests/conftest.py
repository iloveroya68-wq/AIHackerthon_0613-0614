import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def vessel_payload():
    return {
        "vessel_id": "V-PASS-TEST-001",
        "last_coordinate": {"lon": 124.372, "lat": 37.959},
        "last_seen_at": "2026-05-21T08:15:00+09:00",
        "vessel_type": "소형어선",
        "tonnage_tons": 29.0,
        "simulation_hours": 3,
    }
