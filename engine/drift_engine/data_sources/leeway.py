from __future__ import annotations

import csv
from pathlib import Path

from contracts.models import VesselType

DEFAULT_LEEWAY: dict[VesselType, float] = {
    VesselType.SMALL_FISHING: 0.032,
    VesselType.STANDARD_FISHING: 0.025,
    VesselType.PERSON_WITH_LIFEJACKET: 0.015,
    VesselType.LIFE_RAFT: 0.038,
    VesselType.LEISURE_BOAT: 0.045,
}

KEY_MAP = {
    VesselType.SMALL_FISHING: "소형어선",
    VesselType.STANDARD_FISHING: "표준어선",
    VesselType.PERSON_WITH_LIFEJACKET: "구명조끼착용자",
    VesselType.LIFE_RAFT: "구명뗏목_드로그무",
    VesselType.LEISURE_BOAT: "레저보트",
}


class LeewayCatalog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._rates: dict[str, float] | None = None

    def _load(self) -> dict[str, float]:
        if self._rates is None:
            rates: dict[str, float] = {}
            if self.path and self.path.exists():
                with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
                    for row in csv.DictReader(handle):
                        rates[row["object_key"]] = float(row["leeway_rate"])
            self._rates = rates
        return self._rates

    def coefficient(self, vessel_type: VesselType) -> float:
        return self._load().get(KEY_MAP[vessel_type], DEFAULT_LEEWAY[vessel_type])
