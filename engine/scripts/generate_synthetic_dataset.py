from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ENGINE_ROOT.parent
for path in (REPO_ROOT, ENGINE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from drift_engine.features import FEATURE_NAMES  # noqa: E402


def cyclic(value: float, period: float) -> tuple[float, float]:
    angle = 2.0 * math.pi * value / period
    return math.sin(angle), math.cos(angle)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic L3 pipeline dataset")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--records", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [*FEATURE_NAMES, "target_east_m", "target_north_m"]

    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for _ in range(args.records):
            current_direction = rng.uniform(0, 360)
            wind_direction = rng.uniform(0, 360)
            month = int(rng.integers(0, 12))
            hour = int(rng.integers(0, 24))
            current_sin, current_cos = cyclic(current_direction, 360)
            wind_sin, wind_cos = cyclic(wind_direction, 360)
            month_sin, month_cos = cyclic(month, 12)
            hour_sin, hour_cos = cyclic(hour, 24)
            prediction_hours = int(rng.integers(1, 25))
            current_speed = rng.uniform(0.1, 2.2)
            wind_speed = rng.uniform(0.5, 20.0)
            spread = rng.uniform(0.2, 8.0)
            east_std = spread * rng.uniform(0.35, 0.95)
            north_std = spread * rng.uniform(0.35, 0.95)
            major_axis = max(east_std, north_std) * rng.uniform(1.0, 1.8)
            minor_axis = min(east_std, north_std) * rng.uniform(0.6, 1.0)
            orientation = rng.uniform(0, 360)
            orientation_sin, orientation_cos = cyclic(orientation, 360)
            start_lat = rng.uniform(32.2, 38.8)
            start_lon = rng.uniform(124.0, 131.5)
            vessel_type_code = int(rng.integers(0, 5))
            leeway = [0.032, 0.025, 0.015, 0.0375, 0.045][vessel_type_code]
            l2_center_lat = start_lat + rng.normal(0.0, 0.01)
            l2_center_lon = start_lon + rng.normal(0.0, 0.01)
            noise_scale = 80.0 + 25.0 * prediction_hours + 45.0 * spread
            target_east = (
                70.0 * wind_sin * wind_speed
                + 120.0 * current_sin * current_speed
                + rng.normal(0.0, noise_scale)
            )
            target_north = (
                70.0 * wind_cos * wind_speed
                + 120.0 * current_cos * current_speed
                + rng.normal(0.0, noise_scale)
            )
            values = [
                start_lat, start_lon, prediction_hours, vessel_type_code,
                rng.uniform(0, 80), current_speed, current_sin, current_cos,
                wind_speed, wind_sin, wind_cos, leeway, l2_center_lat,
                l2_center_lon, spread, east_std, north_std, major_axis,
                minor_axis, orientation_sin, orientation_cos,
                int(rng.integers(100, 5001)), month_sin, month_cos, hour_sin,
                hour_cos,
            ]
            row = dict(zip(FEATURE_NAMES, values))
            row.update(target_east_m=target_east, target_north_m=target_north)
            writer.writerow(row)


if __name__ == "__main__":
    main()
