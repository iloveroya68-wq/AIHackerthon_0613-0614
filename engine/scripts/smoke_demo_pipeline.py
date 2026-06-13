from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ENGINE_ROOT.parent
for path in (REPO_ROOT, ENGINE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from contracts.models import PredictionRequest, VesselType  # noqa: E402
from drift_engine import RealDriftEngine  # noqa: E402


def main() -> None:
    request = PredictionRequest(
        request_id="demo-pipeline",
        last_coordinate={"lon": 126.2, "lat": 34.5},
        last_seen_at=datetime(2023, 9, 23, 12, tzinfo=ZoneInfo("Asia/Seoul")),
        vessel_type=VesselType.SMALL_FISHING,
        tonnage_tons=4.0,
        simulation_hours=1,
    )
    result = RealDriftEngine().predict(request)
    if not result.l3_correction_applied:
        raise RuntimeError("LightGBM L3 correction was not applied")
    print(json.dumps({
        "current_data_source": result.current_data_source,
        "weather_data_source": result.weather_data_source,
        "l3_correction_applied": result.l3_correction_applied,
        "similar_incidents_count": result.similar_incidents_count,
        "predicted_center": result.predicted_center.model_dump(),
        "search_zone_count": len(result.search_zones["features"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
