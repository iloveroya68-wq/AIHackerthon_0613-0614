"""
ForecastEnvironmentProvider: CMEMS + ECMWF Open Data 예보 NetCDF 파일을
읽어 lat/lon/time 기준으로 내삽하여 EnvironmentData를 반환한다.

사용 전에 .tmp/fetch_forecast.py 를 실행하여
merged_current_wind.nc 파일을 생성해야 한다.
"""
from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from drift_engine.data_sources.models import CurrentData, EnvironmentData, WeatherData

logger = logging.getLogger(__name__)


class ForecastEnvironmentProvider:
    """merged_current_wind.nc (fetch_forecast.py 출력)로부터 환경 데이터 제공.

    첫 get_environment() 호출 시 파일을 1회 로드하고 메모리에 캐시한다.
    파일이 없거나 요청 시각이 예보 범위를 벗어나면 fallback 으로 위임한다.
    """

    def __init__(self, nc_path: Path, fallback=None) -> None:
        self._nc_path = nc_path
        self._fallback = fallback
        self._ds = None

    def _load(self):
        if self._ds is not None:
            return self._ds
        if not self._nc_path.exists():
            raise FileNotFoundError(
                f"예보 파일 없음: {self._nc_path}\n"
                "  → python .tmp/fetch_forecast.py 를 먼저 실행하세요."
            )
        import xarray as xr
        self._ds = xr.open_dataset(self._nc_path)
        logger.info("예보 NetCDF 로드: %s", self._nc_path)
        return self._ds

    def _interp_current(self, ds, lat: float, lon: float, t) -> CurrentData:
        """CMEMS uo/vo → CurrentData."""
        try:
            cur = ds[["uo", "vo"]].interp(latitude=lat, longitude=lon, time=t)
        except Exception:
            # 좌표명이 다를 경우(lat/lon) 시도
            cur = ds[["uo", "vo"]].interp(lat=lat, lon=lon, time=t)

        east = float(cur["uo"].values)
        north = float(cur["vo"].values)

        if not (math.isfinite(east) and math.isfinite(north)):
            # 내삽 실패 시 nearest 선택
            try:
                cur = ds[["uo", "vo"]].sel(
                    latitude=lat, longitude=lon, time=t, method="nearest"
                )
            except Exception:
                cur = ds[["uo", "vo"]].sel(
                    lat=lat, lon=lon, time=t, method="nearest"
                )
            east = float(cur["uo"].values)
            north = float(cur["vo"].values)

        if not (math.isfinite(east) and math.isfinite(north)):
            raise ValueError(f"CMEMS: 유효한 해류값 없음 (lat={lat}, lon={lon})")

        return CurrentData(
            speed_knots=round(math.hypot(east, north) / 0.514444, 4),
            direction_deg=round(math.degrees(math.atan2(east, north)) % 360.0, 3),
            source="CMEMS-FORECAST",
            eastward_mps=east,
            northward_mps=north,
        )

    def _interp_weather(self, ds, lat: float, lon: float, t) -> WeatherData:
        """ECMWF u10/v10 → WeatherData."""
        try:
            wnd = ds[["u10", "v10"]].interp(latitude=lat, longitude=lon, time=t)
        except Exception:
            wnd = ds[["u10", "v10"]].interp(lat=lat, lon=lon, time=t)

        wu = float(wnd["u10"].values)
        wv = float(wnd["v10"].values)

        if not (math.isfinite(wu) and math.isfinite(wv)):
            try:
                wnd = ds[["u10", "v10"]].sel(
                    latitude=lat, longitude=lon, time=t, method="nearest"
                )
            except Exception:
                wnd = ds[["u10", "v10"]].sel(
                    lat=lat, lon=lon, time=t, method="nearest"
                )
            wu = float(wnd["u10"].values)
            wv = float(wnd["v10"].values)

        if not (math.isfinite(wu) and math.isfinite(wv)):
            raise ValueError(f"ECMWF: 유효한 바람값 없음 (lat={lat}, lon={lon})")

        return WeatherData(
            wind_speed_ms=round(math.hypot(wu, wv), 4),
            wind_direction_deg=round(math.degrees(math.atan2(wu, wv)) % 360.0, 3),
            source="ECMWF-OPEN-FORECAST",
        )

    def get_environment(self, lat: float, lon: float, at: datetime) -> EnvironmentData:
        try:
            ds = self._load()
            t = np.datetime64(at.astimezone(UTC).replace(tzinfo=None))
            current = self._interp_current(ds, lat, lon, t)
            weather = self._interp_weather(ds, lat, lon, t)
            return EnvironmentData(weather=weather, current=current)
        except Exception as exc:
            if self._fallback is not None:
                logger.warning("ForecastEnvironmentProvider 실패, fallback 사용: %s", exc)
                return self._fallback.get_environment(lat, lon, at)
            raise
