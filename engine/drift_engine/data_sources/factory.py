from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .environment import EnvironmentProvider, HistoricalBundleProvider
from .land_mask import LandMask
from .leeway import LeewayCatalog


@dataclass(frozen=True)
class DataBundle:
    environment: EnvironmentProvider
    leeway: LeewayCatalog
    land_mask: LandMask


def build_data_bundle(
    source: str,
    data_root: Path | None,
    live_environment: EnvironmentProvider | None = None,
) -> DataBundle:
    if source == "live":
        if live_environment is None:
            raise ValueError("A live environment provider must be supplied by the backend")
        return DataBundle(live_environment, LeewayCatalog(), LandMask())
    if source == "historical":
        if data_root is None:
            raise ValueError("DRIFT_DATA_ROOT is required for historical data")
        return DataBundle(
            HistoricalBundleProvider(data_root),
            LeewayCatalog(data_root / "processed" / "leeway" / "leeway_coefficients.csv"),
            LandMask(data_root / "processed" / "geo" / "land_mask.geojson"),
        )
    raise ValueError(f"Unsupported DRIFT_DATA_SOURCE: {source}")
