"""DRIFT SAR API views — 5 endpoints, synchronous, no Celery."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from django.conf import settings
from pydantic import ValidationError as PydanticValidationError
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from contracts.models import EnginePredictionResult, PredictionRequest, VesselType
from drift_engine.exceptions import DriftEngineError  # type: ignore[import]

from .engine_interface import get_briefing_engine, get_engine, get_risk_engine
from .models import Briefing, Prediction

log = logging.getLogger(__name__)

# Korean waters bounding box (expanded for offshore areas)
_KOR_BBOX = {"min_lon": 123.0, "max_lon": 133.0, "min_lat": 32.0, "max_lat": 40.0}


def custom_exception_handler(exc, context):
    from rest_framework.views import exception_handler

    response = exception_handler(exc, context)
    if response is None:
        log.exception("Unhandled exception in %s", context.get("view"))
        return Response(
            {"detail": "내부 서버 오류가 발생했습니다."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return response


def _check_korean_waters(lon: float, lat: float) -> None:
    if not (_KOR_BBOX["min_lon"] <= lon <= _KOR_BBOX["max_lon"]):
        raise DRFValidationError(
            {"last_coordinate": [f"경도 {lon}°는 한국 근해 범위(123°–133°E) 외입니다."]}
        )
    if not (_KOR_BBOX["min_lat"] <= lat <= _KOR_BBOX["max_lat"]):
        raise DRFValidationError(
            {"last_coordinate": [f"위도 {lat}°는 한국 근해 범위(32°–40°N) 외입니다."]}
        )


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/health/
# ─────────────────────────────────────────────────────────────────────────────

class HealthView(APIView):
    throttle_classes: list = []

    def get(self, request: Request) -> Response:
        from django.conf import settings
        from django.db import connection

        db_ok = True
        try:
            connection.ensure_connection()
        except Exception:
            db_ok = False

        return Response({
            "status": "ok",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "engine": getattr(settings, "DRIFT_ENGINE", "mock"),
            "db": "ok" if db_ok else "error",
        })


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/predictions/
# ─────────────────────────────────────────────────────────────────────────────

class PredictionCreateView(APIView):
    def post(self, request: Request) -> Response:
        # 1. Pydantic validation
        try:
            pred_req = PredictionRequest(**request.data)
        except PydanticValidationError as e:
            return Response({"detail": e.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        # 2. Korean waters check
        _check_korean_waters(pred_req.last_coordinate.lon, pred_req.last_coordinate.lat)

        # 3. Engine
        engine = get_engine()
        try:
            result = engine.predict(pred_req)
        except (ValueError, DriftEngineError) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # 4. Persist
        Prediction.objects.create(
            id=pred_req.request_id,
            vessel_id=pred_req.vessel_id,
            last_lon=pred_req.last_coordinate.lon,
            last_lat=pred_req.last_coordinate.lat,
            last_seen_at=pred_req.last_seen_at,
            vessel_type=pred_req.vessel_type.value,
            tonnage_tons=pred_req.tonnage_tons,
            simulation_hours=pred_req.simulation_hours,
            notes=pred_req.notes,
            engine_result=result.model_dump(mode="json"),
            engine_version=result.current_data_source,
        )

        return Response(result.model_dump(mode="json"), status=status.HTTP_201_CREATED)


class ChatView(APIView):
    def post(self, request: Request) -> Response:
        system_prompt = request.data.get("system_prompt")
        history = request.data.get("history", [])
        user_message = request.data.get("user_message")

        if not isinstance(system_prompt, str) or not isinstance(user_message, str):
            return Response(
                {"detail": "system_prompt and user_message must be strings."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if not isinstance(history, list):
            return Response(
                {"detail": "history must be a list."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if not settings.OPENAI_API_KEY:
            return Response(
                {"detail": "OPENAI_API_KEY is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        messages = [{"role": "system", "content": system_prompt}]
        for message in history:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            text = message.get("text")
            if role in {"user", "model"} and isinstance(text, str):
                messages.append({
                    "role": "assistant" if role == "model" else "user",
                    "content": text,
                })
        messages.append({"role": "user", "content": user_message})

        payload = json.dumps({
            "model": settings.GMS_OPENAI_MODEL,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.3,
            "stream": False,
        }).encode("utf-8")
        upstream_request = UrlRequest(
            f"{settings.GMS_OPENAI_BASE_URL.rstrip('/')}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(upstream_request, timeout=60) as upstream_response:
                result = json.loads(upstream_response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            log.warning("GMS API returned %s: %s", exc.code, error_body)
            return Response(
                {"detail": f"GMS API request failed ({exc.code})."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            log.warning("GMS API request failed: %s", exc)
            return Response(
                {"detail": "Unable to reach the GMS API."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return Response(
                {"detail": "GMS API returned an unexpected response."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"message": content, "model": settings.GMS_OPENAI_MODEL})


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/predictions/{id}/
# ─────────────────────────────────────────────────────────────────────────────

class PredictionDetailView(APIView):
    def get(self, request: Request, pk: str) -> Response:
        try:
            prediction = Prediction.objects.get(pk=pk)
        except Prediction.DoesNotExist:
            return Response({"detail": "예측을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            return Response({"detail": "잘못된 ID 형식입니다."}, status=status.HTTP_400_BAD_REQUEST)

        if prediction.engine_result is None:
            return Response({"detail": "계산 중입니다."}, status=status.HTTP_202_ACCEPTED)

        return Response(prediction.engine_result)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/predictions/{id}/briefing/
# ─────────────────────────────────────────────────────────────────────────────

class PredictionBriefingView(APIView):
    def post(self, request: Request, pk: str) -> Response:
        try:
            prediction = Prediction.objects.get(pk=pk)
        except Prediction.DoesNotExist:
            return Response({"detail": "예측을 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        # Idempotent: return existing briefing
        try:
            briefing = prediction.briefing
            return Response(briefing.briefing_result)
        except Briefing.DoesNotExist:
            pass

        if prediction.engine_result is None:
            return Response(
                {"detail": "예측이 완료된 후 브리핑을 생성할 수 있습니다."},
                status=status.HTTP_409_CONFLICT,
            )

        engine_result = EnginePredictionResult(**prediction.engine_result)
        briefing_fn = get_briefing_engine()
        briefing_result = briefing_fn(
            engine_result,
            last_seen_at=prediction.last_seen_at,
            last_coordinate=(prediction.last_lon, prediction.last_lat),
            vessel_type=prediction.vessel_type,
        )

        Briefing.objects.create(
            prediction=prediction,
            briefing_result=briefing_result.model_dump(mode="json"),
            pdf_url=briefing_result.pdf_url,
        )

        return Response(briefing_result.model_dump(mode="json"), status=status.HTTP_201_CREATED)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/risk/forecast/
# ─────────────────────────────────────────────────────────────────────────────

class RiskForecastView(APIView):
    def get(self, request: Request) -> Response:
        area_name = request.query_params.get("area_name", "수색 해역")
        bbox_str = request.query_params.get("bbox", "124.0,37.5,125.5,38.5")
        t_start_str = request.query_params.get("time_range_start")
        t_end_str = request.query_params.get("time_range_end")
        vt_str = request.query_params.get("vessel_types", "소형어선")

        try:
            bbox = [float(x) for x in bbox_str.split(",")]
            if len(bbox) != 4:
                raise ValueError
        except ValueError:
            return Response(
                {"detail": "bbox는 min_lon,min_lat,max_lon,max_lat 형식이어야 합니다."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        now = datetime.now(tz=timezone.utc)
        try:
            t_start = datetime.fromisoformat(t_start_str) if t_start_str else now
            t_end = datetime.fromisoformat(t_end_str) if t_end_str else now + timedelta(hours=3)
        except ValueError as exc:
            return Response(
                {"detail": f"날짜 형식 오류: {exc}"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        vessel_types: list[VesselType] = []
        for vt in vt_str.split(","):
            try:
                vessel_types.append(VesselType(vt.strip()))
            except ValueError:
                return Response(
                    {"detail": f"유효하지 않은 선박 유형: {vt}"},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

        risk_fn = get_risk_engine()
        result = risk_fn(
            area_name=area_name,
            bbox=bbox,
            time_range_start=t_start,
            time_range_end=t_end,
            vessel_types=vessel_types,
        )

        return Response(result.model_dump(mode="json"))
