from __future__ import annotations

import json
import logging
import math
import os
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from drift_engine.data_sources import CurrentData, EnvironmentData, WeatherData

logger = logging.getLogger(__name__)

KMA_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
KHOA_URL = "https://apis.data.go.kr/1192136/crntFcstTime/getCrntFcstTimeList"

CURRENT_STATIONS = [
    {"code": "DT_0028", "lon": 125.68, "lat": 37.68, "name": "연평도"},
    {"code": "DT_0004", "lon": 126.63, "lat": 37.45, "name": "인천"},
    {"code": "DT_0035", "lon": 126.72, "lat": 35.98, "name": "군산"},
    {"code": "DT_0063", "lon": 126.38, "lat": 34.79, "name": "목포"},
    {"code": "DT_0006", "lon": 129.04, "lat": 35.10, "name": "부산항"},
    {"code": "DT_0061", "lon": 129.11, "lat": 37.49, "name": "동해"},
]


def _get_json(url: str, params: dict[str, object]) -> dict:
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    with urllib.request.urlopen(f"{url}?{query}", timeout=6) as response:
        return json.loads(response.read().decode("utf-8"))


def _latlon_to_kma_grid(lat: float, lon: float) -> tuple[int, int]:
    degrad = math.pi / 180.0
    re, grid = 6371.00877, 5.0
    slat1, slat2 = 30.0 * degrad, 60.0 * degrad
    olon, olat = 126.0 * degrad, 38.0 * degrad
    xo, yo = 43, 136
    re /= grid
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(
        math.tan(math.pi * 0.25 + slat2 * 0.5)
        / math.tan(math.pi * 0.25 + slat1 * 0.5)
    )
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5) ** sn * math.cos(slat1) / sn
    ro = re * sf / math.tan(math.pi * 0.25 + olat * 0.5) ** sn
    ra = re * sf / math.tan(math.pi * 0.25 + lat * degrad * 0.5) ** sn
    theta = max(-math.pi, min(math.pi, lon * degrad - olon)) * sn
    return int(ra * math.sin(theta) + xo + 0.5), int(ro - ra * math.cos(theta) + yo + 0.5)


def _items(payload: dict) -> list[dict]:
    try:
        item = payload["response"]["body"]["items"]["item"]
        return item if isinstance(item, list) else [item]
    except (KeyError, TypeError):
        return []


class PublicMarineEnvironmentProvider:
    """Fetch live wind from KMA and current forecasts from KHOA."""

    def __init__(self) -> None:
        shared_key = os.environ.get("DATA_GO_KR_API_KEY", "")
        self.kma_key = os.environ.get("KMA_API_KEY", shared_key)
        self.khoa_key = os.environ.get("KHOA_API_KEY", shared_key)

    def _weather(self, lat: float, lon: float, at: datetime) -> WeatherData:
        if not self.kma_key:
            return WeatherData(7.5, 315.0, "KMA-FALLBACK", True)
        at_utc = at.astimezone(UTC)
        nx, ny = _latlon_to_kma_grid(lat, lon)
        try:
            payload = _get_json(KMA_URL, {
                "serviceKey": self.kma_key,
                "pageNo": 1,
                "numOfRows": 20,
                "dataType": "JSON",
                "base_date": at_utc.strftime("%Y%m%d"),
                "base_time": at_utc.strftime("%H00"),
                "nx": nx,
                "ny": ny,
            })
            values = {row.get("category"): row.get("obsrValue") for row in _items(payload)}
            return WeatherData(float(values["WSD"]), float(values["VEC"]) % 360, "KMA")
        except Exception as exc:
            logger.warning("KMA request failed; using fallback: %s", exc)
            return WeatherData(7.5, 315.0, "KMA-FALLBACK", True)

    def _current(self, lat: float, lon: float, at: datetime) -> CurrentData:
        if not self.khoa_key:
            return CurrentData(0.8, 45.0, "KHOA-FALLBACK", True)
        at_utc = at.astimezone(UTC)
        station = min(
            CURRENT_STATIONS,
            key=lambda item: math.hypot(item["lon"] - lon, item["lat"] - lat),
        )
        try:
            payload = _get_json(KHOA_URL, {
                "serviceKey": self.khoa_key,
                "pageNo": 1,
                "numOfRows": 24,
                "resultType": "json",
                "obsCode": station["code"],
                "year": at_utc.strftime("%Y"),
                "month": at_utc.strftime("%m"),
                "day": at_utc.strftime("%d"),
            })
            rows = _items(payload)
            if not rows:
                raise ValueError("empty current response")

            def hour(row: dict) -> int:
                value = str(row.get("tmFc") or row.get("tm") or row.get("time") or "")
                return int(value[8:10]) if len(value) >= 10 else 0

            row = min(rows, key=lambda item: abs(hour(item) - at_utc.hour))
            speed_cms = float(row.get("currntSpd") or row.get("speed") or row.get("spd"))
            direction = float(row.get("currntDir") or row.get("drctn") or row.get("dir"))
            return CurrentData(
                round(speed_cms / 51.444, 3),
                round(direction % 360, 1),
                f"KHOA:{station['name']}",
            )
        except Exception as exc:
            logger.warning("KHOA request failed; using fallback: %s", exc)
            return CurrentData(0.8, 45.0, "KHOA-FALLBACK", True)

    def get_environment(self, lat: float, lon: float, at: datetime) -> EnvironmentData:
        return EnvironmentData(
            weather=self._weather(lat, lon, at),
            current=self._current(lat, lon, at),
        )
