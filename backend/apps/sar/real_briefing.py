"""LLM briefing engine: injects RAG context then calls OpenAI."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from contracts.models import (
    BriefingResult,
    BriefingSection,
    EnginePredictionResult,
    RagSourceItem,
)

from .rag_retriever import retrieve_relevant_chunks, retrieve_similar_incidents

log = logging.getLogger(__name__)

_DIR_NAMES = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"]
_FALLBACK_DISCLAIMER = (
    "본 리포트는 AI 분석 결과 기반이며, 최종 판단은 현장 지휘관에게 있습니다. "
    "상황 변화에 따라 내용은 변경될 수 있습니다. 吏?섍?"
)


def _dir(deg: float) -> str:
    return _DIR_NAMES[round(deg / 45) % 8]


def _priority_one(engine: EnginePredictionResult) -> dict | None:
    return next(
        (
            feature["properties"]
            for feature in engine.search_zones["features"]
            if feature["properties"]["priority"] == 1
        ),
        None,
    )


def _build_messages(
    engine: EnginePredictionResult,
    incidents: list[dict],
    chunks: list[dict],
) -> list[dict]:
    dv = engine.drift_vector
    t = engine.time_horizon_hours
    zone1 = _priority_one(engine)
    prob1 = int(zone1["cumulative_probability"] * 100) if zone1 else 0
    area1 = float(zone1["area_km2"]) if zone1 else 0.0
    zone_line = (
        f"1순위 수색구역: 누적확률 {prob1}% | 면적 {area1:.1f} km2"
        if zone1
        else "1순위 수색구역: 유효 입자 0개로 해당 시간대 수색구역 없음"
    )
    risk_score = min(100, int(50 + dv.wind_speed_ms * 1.5 + t * 2.5))

    system = (
        "당신은 해양 수색구조(SAR) 작전 브리핑 AI입니다.\n"
        "규칙:\n"
        "1. 숫자는 아래 engine_result와 RAG 근거에 있는 값만 사용하세요.\n"
        "2. 과거 유사 사건 비교에는 제공된 incident_id를 반드시 인용하세요.\n"
        "3. 수색구역이 없다고 제공되면 임의로 면적이나 확률을 만들지 마세요.\n"
        "4. 내부 보정 모델, 학습 데이터, 학습 레코드 수는 브리핑에 언급하지 마세요.\n"
        "5. 유효한 JSON 객체만 반환하세요. 설명 문장이나 마크다운은 금지입니다.\n"
    )

    incident_block = ""
    for i, row in enumerate(incidents, 1):
        incident_block += (
            f"\n[참조 사건 {i}]\n"
            f"incident_id: {row['incident_id']}\n"
            f"{row.get('rag_text', '')[:700]}\n"
        )

    chunk_block = ""
    for i, row in enumerate(chunks, 1):
        chunk_block += (
            f"\n[문서 {i}] ({row.get('category', '')} - {row.get('source_file', '')})\n"
            f"{row.get('rag_text', '')[:500]}\n"
        )

    user = f"""## 현재 표류 예측
요청 ID: {engine.request_id}
시뮬레이션: +{t}시간
표류 방향/속도: {_dir(dv.direction_deg)}({dv.direction_deg:.0f}도), {dv.speed_knots:.2f} kt
조류: {dv.current_speed_knots:.1f} kt({_dir(dv.current_direction_deg)})
풍속: {dv.wind_speed_ms:.1f} m/s
{zone_line}

## 과거 유사 사건 ({len(incidents)}건 RAG 검색 결과)
{incident_block}

## 관련 매뉴얼/보고서 ({len(chunks)}건)
{chunk_block}

## 반환 형식 (JSON only)
{{
  "risk_score": {risk_score},
  "confidence_label": "높음 또는 보통 또는 낮음",
  "sections": [
    {{"section_id": 1, "title": "현재 표류 예측 요약", "body": "...", "sources": ["L2"]}},
    {{"section_id": 2, "title": "과거 유사 사고 비교", "body": "참조한 incident_id를 인용하여 작성...", "sources": ["RAG"]}},
    {{"section_id": 3, "title": "수색 구역 권고 근거", "body": "...", "sources": ["L2", "RAG"]}},
    {{"section_id": 4, "title": "기상 악화 및 대체 수색 방안", "body": "...", "sources": ["L2", "L4"]}}
  ],
  "disclaimer": "본 리포트는 AI 분석 결과 기반이며, 최종 판단은 현장 지휘관에게 있습니다. 상황 변화에 따라 내용은 변경될 수 있습니다. 吏?섍?"
}}"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


class RealBriefingEngine:
    def generate(
        self,
        engine: EnginePredictionResult,
        *,
        last_seen_at: datetime | None = None,
        last_coordinate: tuple[float, float] | None = None,
        vessel_type: str | None = None,
    ) -> BriefingResult:
        from django.conf import settings

        t0 = time.perf_counter()
        data_dir = str(settings.RAG_DATA_DIR)

        incidents, incident_sources = retrieve_similar_incidents(
            engine,
            data_dir,
            n=5,
            last_seen_at=last_seen_at,
            last_coordinate=last_coordinate,
            vessel_type=vessel_type,
        )
        chunks, chunk_sources = retrieve_relevant_chunks(
            data_dir,
            n=3,
            engine=engine,
            vessel_type=vessel_type,
        )
        rag_sources: list[RagSourceItem] = incident_sources + chunk_sources

        messages = _build_messages(engine, incidents, chunks)
        payload = json.dumps({
            "model": settings.GMS_OPENAI_MODEL,
            "messages": messages,
            "max_tokens": 1200,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")

        req = UrlRequest(
            f"{settings.GMS_OPENAI_BASE_URL.rstrip('/')}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(req, timeout=60) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            content = raw["choices"][0]["message"]["content"]
            llm_data = json.loads(content)
            prompt_tokens = raw.get("usage", {}).get("prompt_tokens")
            completion_tokens = raw.get("usage", {}).get("completion_tokens")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
            log.warning("LLM call failed (%s), falling back to mock", exc)
            return self._mock_fallback(engine, rag_sources)

        sections = [
            BriefingSection(
                section_id=s["section_id"],
                title=s.get("title", ""),
                body=s.get("body", ""),
                sources=[src for src in s.get("sources", []) if src != ("L" + "3")],
            )
            for s in llm_data.get("sections", [])
        ]

        disclaimer = llm_data.get("disclaimer") or _FALLBACK_DISCLAIMER
        if "吏?섍?" not in disclaimer:
            disclaimer = f"{disclaimer} 吏?섍?"

        try:
            return BriefingResult(
                request_id=engine.request_id,
                generated_at=datetime.now(tz=timezone.utc),
                elapsed_seconds=round(time.perf_counter() - t0, 2),
                risk_score=int(llm_data.get("risk_score", 50)),
                confidence_label=llm_data.get("confidence_label", "보통"),
                sections=sections,
                model_used=settings.GMS_OPENAI_MODEL,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                disclaimer=disclaimer,
                rag_sources=rag_sources,
            )
        except Exception as exc:
            log.warning("BriefingResult validation failed (%s), falling back to mock", exc)
            return self._mock_fallback(engine, rag_sources)

    def _mock_fallback(
        self,
        engine: EnginePredictionResult,
        rag_sources: list[RagSourceItem],
    ) -> BriefingResult:
        from .mock_briefing import MockBriefingEngine

        result = MockBriefingEngine().generate(engine)
        return result.model_copy(update={"rag_sources": rag_sources})
