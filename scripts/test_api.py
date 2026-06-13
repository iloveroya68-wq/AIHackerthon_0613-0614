"""Manually verify the backend KMA/KHOA integration."""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT))

from integrations import PublicMarineEnvironmentProvider  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

lat, lon = 34.5, 126.2
environment = PublicMarineEnvironmentProvider().get_environment(
    lat=lat,
    lon=lon,
    at=datetime.now(UTC),
)

print(f"Location: {lat} N, {lon} E")
print(
    "Weather:",
    environment.weather.wind_speed_ms,
    "m/s @",
    environment.weather.wind_direction_deg,
    environment.weather.source,
)
print(
    "Current:",
    environment.current.speed_knots,
    "kt @",
    environment.current.direction_deg,
    environment.current.source,
)
print("data_freshness_ok:", environment.data_freshness_ok)
