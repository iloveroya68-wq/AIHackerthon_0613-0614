"""Mock L4 operational briefing used when the LLM provider is unavailable."""

from __future__ import annotations

import random
from datetime import datetime, timezone

from contracts.models import BriefingResult, BriefingSection, EnginePredictionResult

_DIRECTION_NAMES = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"]


def _dir_name(deg: float) -> str:
    return _DIRECTION_NAMES[round(deg / 45) % 8]


class MockBriefingEngine:
    def generate(self, engine: EnginePredictionResult, **_: object) -> BriefingResult:
        dv = engine.drift_vector
        t = engine.time_horizon_hours
        dir_kor = _dir_name(dv.direction_deg)

        dist_km = dv.speed_knots * 1.852 * t
        zone1_props = next(
            (
                f["properties"]
                for f in engine.search_zones["features"]
                if f["properties"]["priority"] == 1
            ),
            None,
        )
        prob1 = int(zone1_props["cumulative_probability"] * 100) if zone1_props else 0
        area1 = zone1_props["area_km2"] if zone1_props else 0.0

        risk_score = min(100, int(50 + dv.wind_speed_ms * 1.5 + t * 2.5))
        confidence = "높음" if risk_score >= 70 else ("보통" if risk_score >= 50 else "낮음")

        sections = [
            BriefingSection(
                section_id=1,
                title="현재 표류 예측 요약",
                body=(
                    f"분석 기준 +{t}시간, 주요 표류 방향은 {dir_kor}"
                    f"({dv.direction_deg:.0f}도)로 예측됩니다. "
                    f"예상 표류 거리는 약 {dist_km:.1f} km입니다. "
                    f"조류는 {dv.current_speed_knots:.1f} kt, "
                    f"풍속은 {dv.wind_speed_ms:.1f} m/s입니다."
                ),
                sources=["L2"],
            ),
            BriefingSection(
                section_id=2,
                title="과거 유사 사고 비교",
                body=(
                    "LLM 또는 RAG 검색 결과를 사용할 수 없어 과거 유사 사고 세부 비교는 제한됩니다. "
                    "현장에서는 동일 해역 사고 이력과 신고 시각, 기상 악화 여부를 추가 확인하십시오."
                ),
                sources=["RAG"],
            ),
            BriefingSection(
                section_id=3,
                title="수색 구역 권고 근거",
                body=(
                    f"누적 확률 {prob1}% 기준 1순위 수색구역을 우선 투입 구역으로 권고합니다. "
                    f"현재 1순위 면적은 {area1:.1f} km2입니다. "
                    f"표류 방향 {dir_kor}, 조류 {dv.current_speed_knots:.1f} kt, "
                    f"풍속 {dv.wind_speed_ms:.1f} m/s를 함께 고려하십시오."
                ),
                sources=["L2", "RAG"],
            ),
            BriefingSection(
                section_id=4,
                title="기상 악화 및 대체 수색 방안",
                body=(
                    "풍속 15 m/s 초과 또는 파고 상승 시 2순위 수색구역까지 확대하고, "
                    "시야 저하가 발생하면 항공 전력보다 해상 전력 중심의 반복 탐색을 우선 검토하십시오."
                ),
                sources=["L2", "L4"],
            ),
        ]

        return BriefingResult(
            request_id=engine.request_id,
            generated_at=datetime.now(tz=timezone.utc),
            elapsed_seconds=round(random.uniform(28, 52), 1),
            risk_score=risk_score,
            confidence_label=confidence,
            sections=sections,
            model_used="mock-briefing-v1",
            prompt_tokens=None,
            completion_tokens=None,
            pdf_url=None,
            disclaimer=(
                "본 리포트는 AI 분석 결과 기반이며, 최종 판단은 현장 지휘관에게 있습니다. "
                "상황 변화에 따라 내용은 변경될 수 있습니다."
            ),
        )
