from __future__ import annotations

import json
import logging
import warnings
from dataclasses import dataclass

from .config import EngineConfig
from .features import FEATURE_NAMES, build_features
from .geo import move_point

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class L3Result:
    applied: bool
    delta_lon: float = 0.0
    delta_lat: float = 0.0
    similar_incidents_count: int = 0


def predict_l3(
    request: object,
    environment: object,
    l2: object,
    leeway_coefficient: float,
    config: EngineConfig,
) -> L3Result:
    if not config.model_path or not config.model_metadata_path:
        return L3Result(False)
    if not config.model_path.exists() or not config.model_metadata_path.exists():
        return L3Result(False)
    metadata = json.loads(config.model_metadata_path.read_text(encoding="utf-8"))
    records = int(metadata.get("training_records", 0))
    similar_count = int(metadata.get("similar_incidents_count", records))
    if records < config.l3_min_training_records or similar_count < config.l3_min_training_records:
        return L3Result(False, similar_incidents_count=similar_count)
    if metadata.get("features") != FEATURE_NAMES:
        logger.warning("L3 model feature schema does not match runtime features")
        return L3Result(False, similar_incidents_count=similar_count)
    try:
        import joblib

        artifact = joblib.load(config.model_path)
        features = build_features(request, environment, l2, leeway_coefficient)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="X does not have valid feature names",
                category=UserWarning,
            )
            east_m = float(artifact["east_model"].predict(features)[0])
            north_m = float(artifact["north_model"].predict(features)[0])
        final = l2.snapshots[-1]
        center_lon = float(final.lon.mean())
        center_lat = float(final.lat.mean())
        corrected_lon, corrected_lat = move_point(center_lon, center_lat, east_m, north_m)
        return L3Result(
            True,
            corrected_lon - center_lon,
            corrected_lat - center_lat,
            similar_count,
        )
    except Exception as exc:
        logger.warning("L3 prediction failed; using L2 fallback: %s", exc)
        return L3Result(False, similar_incidents_count=similar_count)
