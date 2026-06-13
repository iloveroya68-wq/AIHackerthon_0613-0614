"""Mock L4 operational briefing — generates plausible Korean-language 4-section report."""

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
        similar = engine.similar_incidents_count or 10

        risk_score = min(100, int(50 + dv.wind_speed_ms * 1.5 + t * 2.5))
        confidence = "높음" if risk_score >= 70 else ("보통" if risk_score >= 50 else "낮음")

        sections = [
            BriefingSection(
                section_id=1,
                title="현재 표류 예측 요약",
                body=(
                    f"분석 기준 +{t}시간, 주요 표류 방향은 {dir_kor} "
                    f"({dv.direction_deg:.0f}°)으로 예측됩니다. "
                    f"1순위 구역 내 존재 확률 {prob1}%, 예상 표류 거리 약 {dist_km:.1f} km. "
                    f"조류: {dv.current_speed_knots:.1f} kt ({_dir_name(dv.current_direction_deg)}), "
                    f"풍속: {dv.wind_speed_ms:.1f} m/s."
                ),
                sources=["L1", "L2"],
            ),
            BriefingSection(
                section_id=2,
                title="과거 유사 사고 비교",
                body=(
                    f"최근 5년간 유사 조건 사고 {similar}건 분석 결과, "
                    f"평균 표류 거리 {dist_km * 0.82:.1f} km, "
                    f"2시간 내 발견 확률 58%. "
                    f"L3 보정 모델 {'적용 완료 — 오차 패턴 반영됨' if engine.l3_correction_applied else '미적용 (데이터 부족)'}."
                ),
                sources=["L3"],
            ),
            BriefingSection(
                section_id=3,
                title="1순위 수색 구역 권고 근거",
                body=(
                    f"누적 확률 {prob1}% 등고선 기준 1순위 구역 권고 "
                    f"(면적 {area1:.1f} km²). "
                    f"근거: {dir_kor} 방향 조류 {dv.current_speed_knots:.1f} kt + "
                    f"풍속 {dv.wind_speed_ms:.1f} m/s 복합 작용. "
                    f"해당 해역 수심 20–40 m — 수색 효율 양호."
                ),
                sources=["L1", "L2", "L3"],
            ),
            BriefingSection(
                section_id=4,
                title="기상 악화 시 대체 수색 구역",
                body=(
                    "풍속 15 m/s 초과 또는 파고 2.5 m 초과 시 "
                    "2순위 구역으로 수색 범위 확장을 권고합니다. "
                    f"현재 풍속 {dv.wind_speed_ms:.1f} m/s — "
                    f"{'⚠️ 임박' if dv.wind_speed_ms > 12 else '현재 정상 범위'}. "
                    "기상 모니터링 지속 및 상황 변화 시 즉시 구역 재평가 바랍니다."
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
                "본 리포트는 AI 분석 결과 기반이며, "
                "최종 판단은 현장 지휘관에게 있습니다. "
                "상황 변화에 따라 내용이 변경될 수 있습니다."
            ),
        )
