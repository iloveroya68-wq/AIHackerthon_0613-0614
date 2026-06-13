from datetime import datetime, timezone

from contracts.models import Coordinate, DriftVector, EnginePredictionResult

from apps.sar.rag_retriever import retrieve_relevant_chunks, retrieve_similar_incidents


def _engine() -> EnginePredictionResult:
    return EnginePredictionResult(
        request_id="rag-test",
        computed_at=datetime(2026, 6, 14, 12, tzinfo=timezone.utc),
        elapsed_seconds=1.0,
        time_horizon_hours=3,
        drift_vector=DriftVector(
            direction_deg=90,
            speed_knots=1.0,
            current_speed_knots=0.5,
            current_direction_deg=90,
            wind_speed_ms=5.0,
            wind_direction_deg=180,
            leeway_coefficient=0.032,
        ),
        predicted_center=Coordinate(lon=126.2, lat=34.5),
        search_zones={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "priority": 1,
                        "cumulative_probability": 0.6,
                        "area_km2": 10.0,
                        "center_lon": 126.2,
                        "center_lat": 34.5,
                        "radius_km": 1.0,
                    },
                    "geometry": {"type": "Polygon", "coordinates": []},
                }
            ],
        },
        particle_count=100,
        l3_correction_applied=False,
        data_freshness_ok=True,
    )


def test_similar_incidents_use_original_incident_time(tmp_path):
    (tmp_path / "incidents.csv").write_text(
        "\n".join(
            [
                "incident_id,occurred_at,month,hour,is_night,latitude_decimal,longitude_decimal,weather,vessel_type,incident_type,rag_title,rag_text",
                "day,2020-06-01 12:00,6,12,N,34.5,126.2,양호,어선,기관고장,day title,day text",
                "night,2020-06-01 22:00,6,22,Y,34.5,126.2,양호,어선,기관고장,night title,night text",
            ]
        ),
        encoding="utf-8-sig",
    )
    (tmp_path / "chunks.csv").write_text(
        "doc_id,chunk_id,category,source_file,text,rag_text\n",
        encoding="utf-8-sig",
    )

    incidents, sources = retrieve_similar_incidents(
        _engine(),
        str(tmp_path),
        n=1,
        last_seen_at=datetime(2026, 6, 14, 22, tzinfo=timezone.utc),
        last_coordinate=(126.2, 34.5),
        vessel_type="소형어선",
    )

    assert incidents[0]["incident_id"] == "night"
    assert sources[0].source_id == "night"


def test_relevant_chunks_score_search_manual_above_first_row(tmp_path):
    (tmp_path / "incidents.csv").write_text(
        "incident_id,occurred_at,month,hour,is_night,latitude_decimal,longitude_decimal,weather,vessel_type,incident_type,rag_title,rag_text\n",
        encoding="utf-8-sig",
    )
    (tmp_path / "chunks.csv").write_text(
        "\n".join(
            [
                "doc_id,chunk_id,category,source_file,text,rag_text",
                "a,irrelevant,조사보고서,a.pdf,화물탱크 점검 절차,문서종류: 조사보고서",
                "b,manual,해양경찰수색메뉴얼,b.pdf,해상 조난 실종자 수색 구조 표류 대응,문서종류: 해양경찰수색메뉴얼",
            ]
        ),
        encoding="utf-8-sig",
    )

    chunks, sources = retrieve_relevant_chunks(
        str(tmp_path),
        n=1,
        engine=_engine(),
        vessel_type="소형어선",
    )

    assert chunks[0]["chunk_id"] == "manual"
    assert sources[0].source_id == "manual"
