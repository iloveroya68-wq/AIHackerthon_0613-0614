"""RAG retrieval from local incident and document CSV files.

Loaded once per process via module-level cache; no external vector DB required.
Retrieval is keyword/score-based and uses the original incident context when the
backend passes it in.
"""

from __future__ import annotations

import csv
import math
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from contracts.models import EnginePredictionResult, RagSourceItem

_LEEWAY_TO_VESSEL: dict[float, str] = {
    0.032: "어선",
    0.025: "어선",
    0.015: "고무보트",
    0.0375: "고무보트",
    0.045: "모터보트",
}

_CHUNK_CATEGORY_WEIGHT = {
    "해양경찰수색메뉴얼": 8,
    "해양사고통계": 5,
    "해양사고예방정보": 4,
    "조사보고서": 3,
}
_SEVERE_WEATHER = {"풍랑주의보", "풍랑경보", "태풍주의보", "태풍경보", "저시정"}
_FAIR_WEATHER = {"양호"}


@lru_cache(maxsize=1)
def _load_incidents(data_dir: str) -> list[dict]:
    path = Path(data_dir) / "incidents.csv"
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def _load_chunks(data_dir: str) -> list[dict]:
    path = Path(data_dir) / "chunks.csv"
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _infer_vessel_type(leeway: float) -> str:
    closest = min(_LEEWAY_TO_VESSEL, key=lambda k: abs(k - leeway))
    return _LEEWAY_TO_VESSEL[closest]


def _normalize_vessel_type(value: str | None, leeway: float) -> str:
    if not value:
        return _infer_vessel_type(leeway)
    lower = value.lower()
    if "낚시" in value:
        return "낚시어선"
    if "어선" in value or "?댁꽑" in value:
        return "어선"
    if "고무" in value or "구명" in value or "life" in lower:
        return "고무보트"
    if "보트" in value or "레저" in value or "leisure" in lower:
        return "모터보트"
    return value


def _parse_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _location_score(row: dict, last_coordinate: tuple[float, float] | None) -> tuple[int, float]:
    if last_coordinate is None:
        return 0, float("inf")
    row_lat = _parse_float(row.get("latitude_decimal"))
    row_lon = _parse_float(row.get("longitude_decimal"))
    if row_lat is None or row_lon is None:
        return 0, float("inf")
    distance_km = _haversine_km(last_coordinate[0], last_coordinate[1], row_lon, row_lat)
    if distance_km <= 25:
        return 5, distance_km
    if distance_km <= 75:
        return 4, distance_km
    if distance_km <= 150:
        return 3, distance_km
    if distance_km <= 300:
        return 2, distance_km
    if distance_km <= 600:
        return 1, distance_km
    return 0, distance_km


def _month_score(row: dict, last_seen_at: datetime | None) -> int:
    if last_seen_at is None:
        return 0
    try:
        month = int(row.get("month") or 0)
    except ValueError:
        return 0
    diff = abs(month - last_seen_at.month)
    diff = min(diff, 12 - diff)
    if diff == 0:
        return 2
    if diff == 1:
        return 1
    return 0


def retrieve_similar_incidents(
    engine: EnginePredictionResult,
    data_dir: str,
    n: int = 5,
    *,
    last_seen_at: datetime | None = None,
    last_coordinate: tuple[float, float] | None = None,
    vessel_type: str | None = None,
) -> tuple[list[dict], list[RagSourceItem]]:
    """Return top-n incidents scored against the actual prediction context."""
    incidents = _load_incidents(data_dir)
    normalized_vessel = _normalize_vessel_type(
        vessel_type,
        engine.drift_vector.leeway_coefficient,
    )
    wind_ms = engine.drift_vector.wind_speed_ms
    night_flag = None
    if last_seen_at is not None:
        night_flag = "Y" if last_seen_at.hour < 6 or last_seen_at.hour >= 20 else "N"

    scored: list[tuple[int, float, str, dict]] = []
    for row in incidents:
        score = 0
        if row.get("vessel_type") == normalized_vessel:
            score += 3
        if night_flag is not None and row.get("is_night") == night_flag:
            score += 2
        loc_score, distance_km = _location_score(row, last_coordinate)
        score += loc_score
        score += _month_score(row, last_seen_at)
        weather = row.get("weather", "")
        if wind_ms > 10 and weather in _SEVERE_WEATHER:
            score += 2
        elif wind_ms <= 10 and weather in _FAIR_WEATHER:
            score += 1
        scored.append((score, distance_km, row.get("occurred_at", ""), row))

    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    top = [row for _, _, _, row in scored[:n]]

    rag_items = [
        RagSourceItem(
            source_type="incident",
            source_id=row["incident_id"],
            summary=row.get("rag_title") or row["incident_id"],
            category=row.get("incident_type") or None,
        )
        for row in top
    ]
    return top, rag_items


def retrieve_relevant_chunks(
    data_dir: str,
    n: int = 3,
    *,
    engine: EnginePredictionResult | None = None,
    vessel_type: str | None = None,
) -> tuple[list[dict], list[RagSourceItem]]:
    """Return relevant document chunks, diversified across categories."""
    chunks = _load_chunks(data_dir)

    keywords = {"수색", "구조", "표류", "실종", "해상", "조난", "인명"}
    if vessel_type:
        keywords.add(_normalize_vessel_type(vessel_type, 0.032))
    if engine is not None:
        if engine.drift_vector.wind_speed_ms > 10:
            keywords.update({"풍랑", "기상", "저시정", "악천후"})
        if engine.particle_count == 0:
            keywords.update({"확대", "종료", "실종"})

    scored: list[tuple[int, dict]] = []
    for row in chunks:
        category = row.get("category", "")
        text = f"{row.get('rag_text', '')} {row.get('text', '')}"
        score = _CHUNK_CATEGORY_WEIGHT.get(category, 1)
        for keyword in keywords:
            if keyword and keyword in text:
                score += 2
        scored.append((score, row))

    scored.sort(key=lambda item: item[0], reverse=True)

    selected: list[dict] = []
    used_categories: set[str] = set()
    for _, row in scored:
        category = row.get("category", "")
        if category in used_categories:
            continue
        selected.append(row)
        used_categories.add(category)
        if len(selected) >= n:
            break
    for _, row in scored:
        if len(selected) >= n:
            break
        if row not in selected:
            selected.append(row)

    selected = selected[:n]
    rag_items = [
        RagSourceItem(
            source_type="document",
            source_id=row["chunk_id"],
            summary=f'{row.get("category", "")} - {Path(row.get("source_file", "")).name}',
            category=row.get("category") or None,
        )
        for row in selected
    ]
    return selected, rag_items
