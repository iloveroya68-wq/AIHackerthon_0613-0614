"""Generate L3 training data from real ERA5+CMEMS merged CSV.

For each sampled row the script:
  1. Builds an initial particle cloud around the grid point.
  2. Runs OpenDrift 1-step with CLEAN environment  → true centroid.
  3. Adds measurement noise to the environment.
  4. Runs OpenDrift 1-step with NOISY environment  → predicted centroid / spread.
  5. Builds the L2 particle-feature vector and residual target (east_m, north_m).

Run inside Docker (OpenDrift available there):
  docker-compose run --rm backend \\
    python /engine/scripts/generate_real_dataset.py \\
    --csv  /tmp_data/data/merged_wind_current.csv \\
    --out  /engine/artifacts/real_training.csv \\
    --samples 1000
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ENGINE_ROOT.parent
for _p in (REPO_ROOT, ENGINE_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from contracts.models import VesselType  # noqa: E402
from drift_engine.config import EngineConfig  # noqa: E402
from drift_engine.data_sources.models import CurrentData, EnvironmentData, WeatherData  # noqa: E402
from drift_engine.data_sources.leeway import DEFAULT_LEEWAY  # noqa: E402
from drift_engine.features import FEATURE_NAMES, build_features  # noqa: E402
from drift_engine.l2_monte_carlo import DriftSimulationResult, ParticleSnapshot, run_l2_step  # noqa: E402

# ── 노이즈 파라미터 (관측 불확실성 모사) ──────────────────────────────────────
_NOISE_WIND_SPEED_STD = 0.08   # 풍속 ±8%
_NOISE_WIND_DIR_STD = 12.0     # 풍향 ±12°
_NOISE_CURR_SPEED_STD = 0.12   # 유속 ±12%
_NOISE_CURR_DIR_STD = 18.0     # 유향 ±18°

_VESSEL_TYPES = list(VesselType)
_TONNAGE_RANGE: dict[VesselType, tuple[float, float]] = {
    VesselType.SMALL_FISHING: (1.0, 30.0),
    VesselType.STANDARD_FISHING: (30.0, 200.0),
    VesselType.PERSON_WITH_LIFEJACKET: (0.0, 0.0),
    VesselType.LIFE_RAFT: (0.0, 5.0),
    VesselType.LEISURE_BOAT: (0.5, 20.0),
}


# ── 경량 요청 객체 (PredictionRequest 대신 사용) ─────────────────────────────
@dataclass
class _Coord:
    lat: float
    lon: float


@dataclass
class _Request:
    last_coordinate: _Coord
    last_seen_at: datetime
    vessel_type: VesselType
    simulation_hours: int
    tonnage_tons: float | None
    request_id: str = "training"


# ── ERA5/CMEMS u/v → EnvironmentData 변환 ───────────────────────────────────
def _to_env(
    u_wind: float, v_wind: float,
    u_curr: float, v_curr: float,
) -> EnvironmentData:
    """ERA5 u10/v10 + CMEMS utotal/vtotal → EnvironmentData.

    풍향/유향 모두 "흐르는 방향(to)" 기준 (bearing_components와 동일 약속).
    atan2(east_component, north_component) → 0=북, 시계방향 양수.
    """
    wind_spd = math.sqrt(u_wind ** 2 + v_wind ** 2)
    wind_dir = math.degrees(math.atan2(u_wind, v_wind)) % 360.0

    curr_spd_ms = math.sqrt(u_curr ** 2 + v_curr ** 2)
    curr_dir = math.degrees(math.atan2(u_curr, v_curr)) % 360.0
    curr_spd_kt = curr_spd_ms * 1.94384

    return EnvironmentData(
        weather=WeatherData(
            wind_speed_ms=max(wind_spd, 0.01),
            wind_direction_deg=wind_dir,
            source="era5",
        ),
        current=CurrentData(
            speed_knots=max(curr_spd_kt, 0.001),
            direction_deg=curr_dir,
            source="cmems",
            eastward_mps=u_curr,
            northward_mps=v_curr,
        ),
    )


def _add_noise(
    u_wind: float, v_wind: float,
    u_curr: float, v_curr: float,
    rng: np.random.Generator,
) -> tuple[float, float, float, float]:
    """환경 데이터에 측정 노이즈 추가 (극좌표 방식으로 방향·속도 독립 교란)."""
    # 풍속/풍향 노이즈
    w_spd = math.sqrt(u_wind ** 2 + v_wind ** 2)
    w_dir = math.atan2(u_wind, v_wind)
    nw_spd = max(w_spd * (1.0 + rng.normal(0, _NOISE_WIND_SPEED_STD)), 0.01)
    nw_dir = w_dir + math.radians(rng.normal(0, _NOISE_WIND_DIR_STD))
    nu = nw_spd * math.sin(nw_dir)
    nv = nw_spd * math.cos(nw_dir)

    # 유속/유향 노이즈
    c_spd = math.sqrt(u_curr ** 2 + v_curr ** 2)
    c_dir = math.atan2(u_curr, v_curr)
    nc_spd = max(c_spd * (1.0 + rng.normal(0, _NOISE_CURR_SPEED_STD)), 0.001)
    nc_dir = c_dir + math.radians(rng.normal(0, _NOISE_CURR_DIR_STD))
    ncu = nc_spd * math.sin(nc_dir)
    ncv = nc_spd * math.cos(nc_dir)

    return nu, nv, ncu, ncv


def _initial_particles(
    lat: float, lon: float, config: EngineConfig, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """시작 위경도 주변에 원형 확산 입자 배열 생성 (훈련·추론 동일 방식)."""
    n = config.particle_count
    angles = rng.uniform(0.0, 2.0 * math.pi, n)
    radii = config.seed_radius_m * np.sqrt(rng.uniform(0.0, 1.0, n))
    cos_lat = max(0.01, math.cos(math.radians(lat)))
    lons = lon + (radii * np.sin(angles)) / (111_320.0 * cos_lat)
    lats = lat + (radii * np.cos(angles)) / 111_320.0
    return lons, lats


def _process_sample(
    lat: float,
    lon: float,
    t: datetime,
    u_wind: float,
    v_wind: float,
    u_curr: float,
    v_curr: float,
    config: EngineConfig,
    rng: np.random.Generator,
) -> dict | None:
    vessel_type = _VESSEL_TYPES[int(rng.integers(0, len(_VESSEL_TYPES)))]
    t_min, t_max = _TONNAGE_RANGE[vessel_type]
    tonnage = float(rng.uniform(t_min, t_max)) if t_max > 0 else None

    request = _Request(
        last_coordinate=_Coord(lat=lat, lon=lon),
        last_seen_at=t,
        vessel_type=vessel_type,
        simulation_hours=1,
        tonnage_tons=tonnage,
    )

    step_time = t.astimezone(UTC).replace(tzinfo=None)
    # 두 실행에 동일한 초기 입자 배열 사용 → 환경 차이만 격리
    init_lons, init_lats = _initial_particles(lat, lon, config, rng)

    clean_env = _to_env(u_wind, v_wind, u_curr, v_curr)
    clean_snap = run_l2_step(init_lons, init_lats, step_time, clean_env, config, hour=1)
    true_center_lon = float(clean_snap.lon.mean())
    true_center_lat = float(clean_snap.lat.mean())

    nu, nv, ncu, ncv = _add_noise(u_wind, v_wind, u_curr, v_curr, rng)
    noisy_env = _to_env(nu, nv, ncu, ncv)
    noisy_snap = run_l2_step(init_lons, init_lats, step_time, noisy_env, config, hour=1)

    step_l2 = DriftSimulationResult([noisy_snap], len(noisy_snap.lon), "opendrift-leeway")
    features = build_features(request, noisy_env, step_l2, DEFAULT_LEEWAY[vessel_type])

    noisy_center_lon = float(noisy_snap.lon.mean())
    noisy_center_lat = float(noisy_snap.lat.mean())
    cos_lat = math.cos(math.radians(noisy_center_lat))
    target_east_m = (true_center_lon - noisy_center_lon) * 111_320.0 * cos_lat
    target_north_m = (true_center_lat - noisy_center_lat) * 111_320.0

    row = dict(zip(FEATURE_NAMES, features[0].tolist()))
    row["target_east_m"] = target_east_m
    row["target_north_m"] = target_north_m
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate real-data L3 training dataset")
    parser.add_argument("--csv", type=Path, required=True, help="merged_wind_current.csv 경로")
    parser.add_argument("--out", type=Path, required=True, help="출력 학습 CSV 경로")
    parser.add_argument("--samples", type=int, default=1000, help="생성할 샘플 수 (기본 1000)")
    parser.add_argument("--particles", type=int, default=200, help="OpenDrift 입자 수 (기본 200)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    config = EngineConfig(
        particle_count=args.particles,
        seed_radius_m=500.0,
        random_seed=int(rng.integers(0, 100_000)),
        l2_engine="opendrift",
    )

    print(f"병합 CSV 로드: {args.csv}")
    df = pd.read_csv(args.csv, parse_dates=["time"])
    df = df.dropna().reset_index(drop=True)
    print(f"  유효 행: {len(df):,}개")

    n = min(args.samples, len(df))
    indices = rng.choice(len(df), size=n, replace=False)
    print(f"  샘플링: {n}개 (particles/call={args.particles})")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [*FEATURE_NAMES, "target_east_m", "target_north_m"]

    written = skipped = 0
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()

        for i, idx in enumerate(indices):
            row = df.iloc[int(idx)]
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            t = row["time"]
            if hasattr(t, "to_pydatetime"):
                t = t.to_pydatetime()
            if t.tzinfo is None:
                t = t.replace(tzinfo=UTC)

            try:
                out_row = _process_sample(
                    lat, lon, t,
                    float(row["u10"]), float(row["v10"]),
                    float(row["utotal"]), float(row["vtotal"]),
                    config, rng,
                )
                writer.writerow(out_row)
                written += 1
            except Exception as exc:  # noqa: BLE001
                warnings.warn(f"샘플 {idx} 실패: {exc}")
                skipped += 1

            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{n}] 완료={written} 건너뜀={skipped}")

    print(f"\n완료: {written}개 저장, {skipped}개 건너뜀 → {args.out}")


if __name__ == "__main__":
    main()
