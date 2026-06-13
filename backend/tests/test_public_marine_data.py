from __future__ import annotations

from datetime import UTC, datetime

from integrations import PublicMarineEnvironmentProvider


def test_public_provider_uses_fallback_without_api_keys(monkeypatch):
    for name in ("DATA_GO_KR_API_KEY", "KMA_API_KEY", "KHOA_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    environment = PublicMarineEnvironmentProvider().get_environment(
        lat=34.5,
        lon=126.2,
        at=datetime(2026, 6, 12, tzinfo=UTC),
    )

    assert environment.weather.source == "KMA-FALLBACK"
    assert environment.current.source == "KHOA-FALLBACK"
    assert environment.data_freshness_ok is False
