from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WeatherData:
    wind_speed_ms: float
    wind_direction_deg: float
    source: str
    is_fallback: bool = False


@dataclass(frozen=True)
class CurrentData:
    speed_knots: float
    direction_deg: float
    source: str
    is_fallback: bool = False
    eastward_mps: float | None = None
    northward_mps: float | None = None


@dataclass(frozen=True)
class EnvironmentData:
    weather: WeatherData
    current: CurrentData

    @property
    def data_freshness_ok(self) -> bool:
        return not (self.weather.is_fallback or self.current.is_fallback)
