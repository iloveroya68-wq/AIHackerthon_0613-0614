"""
Engine interface: the only coupling point between the API and drift engine.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from contracts.models import (
        BriefingResult,
        EnginePredictionResult,
        PredictionRequest,
        RiskForecastResult,
    )


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

class DriftEngineProtocol(Protocol):
    def predict(self, request: PredictionRequest) -> EnginePredictionResult: ...


BriefingGeneratorProtocol = Callable[..., "BriefingResult"]

RiskGeneratorProtocol = Callable[..., "RiskForecastResult"]


# ---------------------------------------------------------------------------
# Factory functions — swap MockEngine ↔ RealEngine via DRIFT_ENGINE env var
# ---------------------------------------------------------------------------

def get_engine() -> DriftEngineProtocol:
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured

    engine_name = getattr(settings, "DRIFT_ENGINE", "mock")
    if engine_name == "mock":
        from .mock_engine import MockEngine
        return MockEngine()

    if engine_name == "real":
        import os
        from pathlib import Path

        from drift_engine import RealDriftEngine  # type: ignore[import]
        from drift_engine.config import EngineConfig
        from drift_engine.data_sources import build_data_bundle

        config = EngineConfig.from_env()

        if config.data_source == "forecast":
            from drift_engine.data_sources import DataBundle
            from drift_engine.data_sources.land_mask import LandMask
            from drift_engine.data_sources.leeway import LeewayCatalog
            from integrations import ForecastEnvironmentProvider, MergedCSVEnvironmentProvider

            nc_path = Path(os.environ.get(
                "DRIFT_FORECAST_PATH",
                "/tmp_data/forecast/merged_current_wind.nc",
            ))
            csv_path = Path(os.environ.get(
                "DRIFT_CSV_PATH",
                "/tmp_data/data/merged_wind_current.csv",
            ))
            land_mask_path = Path(os.environ.get(
                "DRIFT_LAND_MASK_PATH",
                "/data/modeling_inputs/processed/geo/land_mask.geojson",
            ))
            # fallback 우선순위: CMEMS+ECMWF NC → ERA5+CMEMS CSV → 오류
            csv_fallback = MergedCSVEnvironmentProvider(csv_path) if csv_path.exists() else None
            provider = ForecastEnvironmentProvider(nc_path, fallback=csv_fallback)
            data_bundle = DataBundle(
                environment=provider,
                leeway=LeewayCatalog(),
                land_mask=LandMask(land_mask_path if land_mask_path.exists() else None),
            )
            return RealDriftEngine(config, data_bundle=data_bundle)

        if config.data_source == "live":
            from integrations import PublicMarineEnvironmentProvider

            data_bundle = build_data_bundle(
                "live",
                None,
                live_environment=PublicMarineEnvironmentProvider(),
            )
            return RealDriftEngine(config, data_bundle=data_bundle)

        return RealDriftEngine(config)

    raise ImproperlyConfigured(
        f"Unsupported DRIFT_ENGINE={engine_name!r}; expected 'mock' or 'real'"
    )


def get_briefing_engine() -> BriefingGeneratorProtocol:
    from django.conf import settings

    if getattr(settings, "OPENAI_API_KEY", ""):
        from .real_briefing import RealBriefingEngine
        return RealBriefingEngine().generate

    from .mock_briefing import MockBriefingEngine
    return MockBriefingEngine().generate


def get_risk_engine() -> RiskGeneratorProtocol:
    from .mock_risk import MockRiskEngine

    return MockRiskEngine().forecast
