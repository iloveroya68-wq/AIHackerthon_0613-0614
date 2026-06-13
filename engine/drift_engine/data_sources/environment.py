from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from .models import CurrentData, EnvironmentData, WeatherData


class EnvironmentProvider(Protocol):
    def get_environment(self, lat: float, lon: float, at: datetime) -> EnvironmentData: ...


class HistoricalBundleProvider:
    """CMEMS current plus KHOA weather from a versioned local data bundle."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.cmems_path = data_root / "raw" / "cmems" / "mokpo_surface_current.nc"
        self.weather_path = data_root / "processed" / "khoa" / "khoa_mokpo_weather_hourly.csv"
        self._dataset = None
        self._weather = None

    def _load_dataset(self):
        if self._dataset is None:
            import xarray as xr

            if not self.cmems_path.exists():
                raise FileNotFoundError(f"CMEMS data not found: {self.cmems_path}")
            self._dataset = xr.open_dataset(self.cmems_path)
        return self._dataset

    def _load_weather(self):
        if self._weather is None:
            import pandas as pd

            if not self.weather_path.exists():
                raise FileNotFoundError(f"KHOA weather data not found: {self.weather_path}")
            frame = pd.read_csv(self.weather_path, parse_dates=["timestamp"])
            self._weather = frame.sort_values("timestamp").set_index("timestamp")
        return self._weather

    @staticmethod
    def _naive_utc(at: datetime) -> datetime:
        if at.tzinfo is None:
            return at
        return at.astimezone(UTC).replace(tzinfo=None)

    @staticmethod
    def _naive_kst(at: datetime) -> datetime:
        if at.tzinfo is None:
            return at
        return at.astimezone(ZoneInfo("Asia/Seoul")).replace(tzinfo=None)

    def _current(self, lat: float, lon: float, at: datetime) -> CurrentData:
        import numpy as np

        dataset = self._load_dataset()
        at_utc = self._naive_utc(at)
        time_min = np.datetime64(dataset.time.values[0])
        time_max = np.datetime64(dataset.time.values[-1])
        target_time = np.datetime64(at_utc)
        if not time_min <= target_time <= time_max:
            raise ValueError(f"CMEMS time outside bundle range: {at_utc.isoformat()}")
        lat_min, lat_max = float(dataset.latitude.min()), float(dataset.latitude.max())
        lon_min, lon_max = float(dataset.longitude.min()), float(dataset.longitude.max())
        if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
            raise ValueError(f"CMEMS coordinate outside bundle range: {lat}, {lon}")

        surface = dataset[["uo", "vo"]].isel(depth=0).interp(
            time=target_time,
            latitude=lat,
            longitude=lon,
        )
        east = float(surface["uo"].values)
        north = float(surface["vo"].values)
        if not math.isfinite(east) or not math.isfinite(north):
            # Coastal interpolation can cross masked land cells; nearest valid grid is safer.
            surface = dataset[["uo", "vo"]].isel(depth=0).sel(
                time=target_time,
                latitude=lat,
                longitude=lon,
                method="nearest",
            )
            east = float(surface["uo"].values)
            north = float(surface["vo"].values)
        if not math.isfinite(east) or not math.isfinite(north):
            raise ValueError("CMEMS returned no valid current at the requested point")
        speed_mps = math.hypot(east, north)
        direction = math.degrees(math.atan2(east, north)) % 360.0
        return CurrentData(
            speed_knots=round(speed_mps / 0.514444, 4),
            direction_deg=round(direction, 3),
            source=f"CMEMS:{self.cmems_path.name}",
            eastward_mps=east,
            northward_mps=north,
        )

    def _weather_at(self, at: datetime) -> WeatherData:
        import pandas as pd

        frame = self._load_weather()
        target = pd.Timestamp(self._naive_kst(at))
        index = frame.index.get_indexer([target], method="nearest")[0]
        if index < 0:
            raise ValueError("KHOA weather bundle has no matching row")
        row = frame.iloc[index]
        observed_at = frame.index[index]
        if abs(observed_at - target) > pd.Timedelta(hours=2):
            raise ValueError(f"KHOA weather time outside bundle range: {target}")
        return WeatherData(
            wind_speed_ms=float(row["wind_speed_mps"]),
            wind_direction_deg=float(row["wind_direction_deg"]),
            source=f"KHOA-HISTORY:{row['station_name']}",
        )

    def get_environment(self, lat: float, lon: float, at: datetime) -> EnvironmentData:
        return EnvironmentData(weather=self._weather_at(at), current=self._current(lat, lon, at))
