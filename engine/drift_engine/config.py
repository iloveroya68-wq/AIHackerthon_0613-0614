from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EngineConfig:
    particle_count: int = 1000
    seed_radius_m: float = 500.0
    random_seed: int = 42
    l2_engine: str = "opendrift"
    data_source: str = "live"
    data_root: Path | None = None
    model_path: Path | None = None
    model_metadata_path: Path | None = None
    l3_min_training_records: int = 30

    @classmethod
    def from_env(cls) -> EngineConfig:
        model_path = os.environ.get("DRIFT_MODEL_PATH")
        metadata_path = os.environ.get("DRIFT_MODEL_METADATA_PATH")
        data_root = os.environ.get("DRIFT_DATA_ROOT")
        return cls(
            particle_count=int(os.environ.get("ENGINE_PARTICLE_COUNT", "1000")),
            seed_radius_m=float(os.environ.get("DRIFT_SEED_RADIUS_M", "500")),
            random_seed=int(os.environ.get("DRIFT_RANDOM_SEED", "42")),
            l2_engine=os.environ.get("DRIFT_L2_ENGINE", "opendrift").lower(),
            data_source=os.environ.get("DRIFT_DATA_SOURCE", "live").lower(),
            data_root=Path(data_root) if data_root else None,
            model_path=Path(model_path) if model_path else None,
            model_metadata_path=Path(metadata_path) if metadata_path else None,
            l3_min_training_records=int(
                os.environ.get("ENGINE_L3_MIN_TRAINING_RECORDS", "30")
            ),
        )
