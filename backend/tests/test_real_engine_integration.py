from __future__ import annotations

import json

import pytest
from django.test import override_settings
from drift_engine.data_sources import (
    CurrentData,
    EnvironmentData,
    WeatherData,
)


@pytest.mark.django_db
@override_settings(DRIFT_ENGINE="real", DRIFT_L2_ENGINE="synthetic")
def test_prediction_api_with_real_engine(api_client, vessel_payload, monkeypatch):
    environment = EnvironmentData(
        weather=WeatherData(8.0, 315.0, source="TEST-KMA"),
        current=CurrentData(0.8, 45.0, source="TEST-KHOA"),
    )
    class StaticEnvironmentProvider:
        def get_environment(self, *_args):
            return environment

    provider = StaticEnvironmentProvider()
    monkeypatch.setattr("integrations.PublicMarineEnvironmentProvider", lambda: provider)
    monkeypatch.setenv("DRIFT_DATA_SOURCE", "live")
    monkeypatch.setenv("ENGINE_PARTICLE_COUNT", "200")
    monkeypatch.setenv("DRIFT_L2_ENGINE", "synthetic")

    response = api_client.post(
        "/api/v1/predictions/",
        data=json.dumps(vessel_payload),
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["particle_count"] == 200
    assert data["current_data_source"] == "TEST-KHOA"
    assert data["weather_data_source"] == "TEST-KMA"
    assert data["l3_correction_applied"] is False
    assert len(data["time_steps"]) == vessel_payload["simulation_hours"]
