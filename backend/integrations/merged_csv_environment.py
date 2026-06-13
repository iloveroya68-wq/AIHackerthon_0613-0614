"""
MergedCSVEnvironmentProvider: merged_wind_current.csv (ERA5+CMEMS 병합)로부터
환경 데이터를 제공한다.

시간·위경도 기준으로 가장 가까운 행을 선택한다.
fetch_forecast.py 없이 기존 병합 CSV로 즉시 테스트할 때 사용.
"""
from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from pathlib import Path

from drift_engine.data_sources.models import CurrentData, EnvironmentData, WeatherData

logger = logging.getLogger(__name__)


class MergedCSVEnvironmentProvider:
    """ERA5+CMEMS 병합 CSV → EnvironmentData.

    시각·위경도에 가장 가까운 행을 pandas nearest lookup으로 선택.
    첫 호출 시 CSV를 메모리에 1회 로드한다.
    """

    def __init__(self, csv_path: Path) -> None:
        self._csv_path = csv_path
        self._df = None

    def _load(self):
        if self._df is not None:
            return self._df
        if not self._csv_path.exists():
            raise FileNotFoundError(
                f"병합 CSV 없음: {self._csv_path}\n"
                "  → .tmp/data/merged_wind_current.csv 가 필요합니다."
            )
        import pandas as pd
        df = pd.read_csv(self._csv_path, parse_dates=["time"])
        df = df.dropna().reset_index(drop=True)
        # 시간을 timezone-aware UTC로 통일
        if df["time"].dt.tz is None:
            df["time"] = df["time"].dt.tz_localize("UTC")
        self._df = df
        logger.info("병합 CSV 로드 완료: %d행 (%s)", len(df), self._csv_path.name)
        return self._df

    def get_environment(self, lat: float, lon: float, at: datetime) -> EnvironmentData:
        import numpy as np
        df = self._load()

        at_utc = at.astimezone(UTC)

        # 1. 시간 차이 기준 가장 가까운 행들 필터
        time_diff = (df["time"] - at_utc).abs()
        min_diff = time_diff.min()
        candidates = df[time_diff == min_diff].copy()

        # 2. 그 중 위경도 가장 가까운 행 선택
        candidates["_dist"] = np.hypot(
            candidates["latitude"] - lat,
            candidates["longitude"] - lon,
        )
        row = candidates.loc[candidates["_dist"].idxmin()]

        u10 = float(row["u10"])
        v10 = float(row["v10"])
        uo = float(row["utotal"])
        vo = float(row["vtotal"])

        wind_spd = math.hypot(u10, v10)
        wind_dir = math.degrees(math.atan2(u10, v10)) % 360.0
        curr_spd_ms = math.hypot(uo, vo)
        curr_dir = math.degrees(math.atan2(uo, vo)) % 360.0

        return EnvironmentData(
            weather=WeatherData(
                wind_speed_ms=max(wind_spd, 0.01),
                wind_direction_deg=wind_dir,
                source=f"ERA5-CSV:{row['time'].strftime('%Y-%m-%dT%H')}",
            ),
            current=CurrentData(
                speed_knots=max(curr_spd_ms / 0.514444, 0.001),
                direction_deg=curr_dir,
                source=f"CMEMS-CSV:{row['time'].strftime('%Y-%m-%dT%H')}",
                eastward_mps=uo,
                northward_mps=vo,
            ),
        )
