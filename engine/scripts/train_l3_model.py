from __future__ import annotations

import argparse
import csv
import json
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ENGINE_ROOT.parent
for path in (REPO_ROOT, ENGINE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from drift_engine.features import FEATURE_NAMES  # noqa: E402


def load_dataset(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Training dataset is empty")
    required = [*FEATURE_NAMES, "target_east_m", "target_north_m"]
    missing = [name for name in required if name not in rows[0]]
    if missing:
        raise ValueError(f"Missing training columns: {missing}")
    features = np.asarray([[float(row[name]) for name in FEATURE_NAMES] for row in rows])
    east = np.asarray([float(row["target_east_m"]) for row in rows])
    north = np.asarray([float(row["target_north_m"]) for row in rows])
    return features, east, north


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the DRIFT L3 residual models")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()

    try:
        import joblib
        from lightgbm import LGBMRegressor
    except ImportError as exc:
        raise SystemExit("Install drift-engine[ml] before training") from exc

    x, east, north = load_dataset(args.input)
    common = {
        "n_estimators": 300,
        "learning_rate": 0.03,
        "num_leaves": 31,
        "random_state": 42,
        "verbosity": -1,
    }
    east_model = LGBMRegressor(**common).fit(x, east)
    north_model = LGBMRegressor(**common).fit(x, north)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="X does not have valid feature names",
            category=UserWarning,
        )
        predicted_east = east_model.predict(x)
        predicted_north = north_model.predict(x)
    endpoint_error_km = np.hypot(predicted_east - east, predicted_north - north) / 1000.0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"east_model": east_model, "north_model": north_model}, args.output)
    metadata = {
        "model_version": "l3-0.1.0",
        "model_type": "LightGBMRegressorPair",
        "features": FEATURE_NAMES,
        "training_records": int(len(x)),
        "created_at": datetime.now(tz=UTC).isoformat(),
        "metrics": {
            "training_endpoint_mae_km": float(np.mean(endpoint_error_km)),
            "training_endpoint_p90_km": float(np.percentile(endpoint_error_km, 90)),
        },
    }
    args.metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
