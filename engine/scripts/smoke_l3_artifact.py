from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ENGINE_ROOT.parent
for path in (REPO_ROOT, ENGINE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from contracts.models import PredictionRequest, VesselType  # noqa: E402
from drift_engine import RealDriftEngine  # noqa: E402
from drift_engine.config import EngineConfig  # noqa: E402
from drift_engine.data_sources import (  # noqa: E402
    CurrentData,
    DataBundle,
    EnvironmentData,
    LandMask,
    LeewayCatalog,
    WeatherData,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load and apply a trained L3 artifact")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()

    environment = EnvironmentData(
        weather=WeatherData(8.0, 315.0, source="TRAIN-SMOKE-KMA"),
        current=CurrentData(0.8, 45.0, source="TRAIN-SMOKE-KHOA"),
    )
    class StaticEnvironmentProvider:
        def get_environment(self, *_args):
            return environment

    bundle = DataBundle(StaticEnvironmentProvider(), LeewayCatalog(), LandMask())
    request = PredictionRequest(
        last_coordinate={"lon": 126.375, "lat": 34.779},
        last_seen_at=datetime(2026, 6, 11, 9, tzinfo=UTC),
        vessel_type=VesselType.SMALL_FISHING,
        tonnage_tons=4.0,
        simulation_hours=1,
    )
    result = RealDriftEngine(EngineConfig(
        particle_count=100,
        l2_engine="opendrift",
        model_path=args.model,
        model_metadata_path=args.metadata,
        l3_min_training_records=30,
    ), data_bundle=bundle).predict(request)
    assert result.l3_correction_applied
    assert result.similar_incidents_count >= 30
    assert result.weight_l1 == 0.0
    assert result.weight_l2 == 1.0
    assert result.weight_l3 == 0.0
    print("LightGBM artifact load and L3 prediction smoke test passed")


if __name__ == "__main__":
    main()
