"""Mock P1 proactive risk forecast — generates a grid-based DRI Heatmap."""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from contracts.models import (
    RecommendedAction,
    RiskCause,
    RiskForecastResult,
    RiskLevel,
    VesselType,
)


class MockRiskEngine:
    def forecast(
        self,
        area_name: str,
        bbox: list[float],
        time_range_start: datetime,
        time_range_end: datetime,
        vessel_types: list[VesselType],
    ) -> RiskForecastResult:
        min_lon, min_lat, max_lon, max_lat = bbox

        # Seed from area + time
        key = f"{area_name}:{min_lon:.2f}:{min_lat:.2f}:{time_range_start.hour}"
        seed = int(hashlib.md5(key.encode()).hexdigest(), 16) % (2**31)
        rng = random.Random(seed)

        # Build grid (3×3 cells for simplicity)
        cols, rows = 3, 3
        cell_w = (max_lon - min_lon) / cols
        cell_h = (max_lat - min_lat) / rows

        features: list[dict[str, Any]] = []
        area_dri_scores: list[float] = []

        for row in range(rows):
            for col in range(cols):
                lon0 = min_lon + col * cell_w
                lat0 = min_lat + row * cell_h
                lon1, lat1 = lon0 + cell_w, lat0 + cell_h

                # Center cells → higher risk
                cx = abs(col - (cols - 1) / 2) / ((cols - 1) / 2)  # 0=center, 1=edge
                cy = abs(row - (rows - 1) / 2) / ((rows - 1) / 2)
                base_dri = 0.8 - (cx + cy) * 0.25
                dri = max(0.05, min(0.99, base_dri + rng.uniform(-0.12, 0.12)))
                area_dri_scores.append(dri)

                if dri >= 0.65:
                    level = RiskLevel.HIGH
                elif dri >= 0.35:
                    level = RiskLevel.CAUTION
                else:
                    level = RiskLevel.WATCH

                features.append({
                    "type": "Feature",
                    "properties": {
                        "risk_level": level.value,
                        "dri_score": round(dri, 3),
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [round(lon0, 5), round(lat0, 5)],
                            [round(lon1, 5), round(lat0, 5)],
                            [round(lon1, 5), round(lat1, 5)],
                            [round(lon0, 5), round(lat1, 5)],
                            [round(lon0, 5), round(lat0, 5)],
                        ]],
                    },
                })

        overall_dri = round(sum(area_dri_scores) / len(area_dri_scores), 3)
        peak_offset = timedelta(
            minutes=rng.randint(30, int((time_range_end - time_range_start).total_seconds() / 60 * 0.7))
        )
        peak_time = time_range_start + peak_offset

        wind_ms = round(rng.uniform(8.0, 18.0), 1)
        wave_m = round(rng.uniform(1.0, 2.5), 1)
        current_kt = round(rng.uniform(0.5, 3.0), 2)

        has_tidal = rng.random() > 0.3
        tidal_offset = timedelta(minutes=rng.randint(15, 90))
        tidal_time = time_range_start + tidal_offset if has_tidal else None

        high_area = round(
            sum(
                cell_w * 111.0 * cell_h * 111.0
                for dri in area_dri_scores
                if dri >= 0.65
            ),
            1,
        )
        vessels_at_risk = rng.randint(80, 200)

        return RiskForecastResult(
            forecasted_at=datetime.now(tz=timezone.utc),
            area_name=area_name,
            bbox=bbox,
            time_range_start=time_range_start,
            time_range_end=time_range_end,
            peak_risk_time=peak_time,
            vessel_types_targeted=vessel_types,
            risk_grid={"type": "FeatureCollection", "features": features},
            dri_score=overall_dri,
            dri_percentile=round(overall_dri * 100 * rng.uniform(0.9, 1.1), 1),
            risk_causes=[
                RiskCause(
                    factor="조류 반전",
                    description=f"{peak_time.strftime('%H:%M')} ±20분 조류 반전 예정",
                    severity=RiskLevel.HIGH,
                ),
                RiskCause(
                    factor="풍속 강화",
                    description=f"북서풍 최대 {wind_ms} m/s 예보",
                    severity=RiskLevel.CAUTION if wind_ms < 15 else RiskLevel.HIGH,
                ),
                RiskCause(
                    factor="파고 상승",
                    description=f"유의파고 최대 {wave_m} m 예상",
                    severity=RiskLevel.CAUTION,
                ),
            ],
            recommended_actions=[
                RecommendedAction(priority=1, action="순찰정 사전 배치", target="고위험 해역 북서 경계선"),
                RecommendedAction(priority=2, action="V-Pass 주의 알림 발송", target=f"조업 선박 {vessels_at_risk}척"),
                RecommendedAction(priority=3, action="출항 주의 안내 송출", target="해양경계방송"),
            ],
            max_wind_speed_ms=wind_ms,
            max_wave_height_m=wave_m,
            max_current_speed_kt=current_kt,
            tidal_reversal_time=tidal_time,
            vessels_at_risk_count=vessels_at_risk,
            high_risk_area_km2=high_area,
        )
