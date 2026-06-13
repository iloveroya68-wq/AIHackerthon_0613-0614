from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class LandMask:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._geometry = None

    @property
    def available(self) -> bool:
        return bool(self.path and self.path.exists())

    def _load(self):
        if self._geometry is None and self.available:
            from shapely.geometry import shape
            from shapely.ops import unary_union

            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self._geometry = unary_union([shape(feature["geometry"]) for feature in payload["features"]])
        return self._geometry

    def filter_water(self, lons: np.ndarray, lats: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        geometry = self._load()
        if geometry is None:
            return lons, lats
        from shapely.geometry import Point

        water = np.asarray([
            not geometry.covers(Point(float(lon), float(lat)))
            for lon, lat in zip(lons, lats, strict=True)
        ])
        return lons[water], lats[water]

    def filter_water_path(
        self,
        start_lons: np.ndarray,
        start_lats: np.ndarray,
        end_lons: np.ndarray,
        end_lats: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """END 위치가 물이고, 이동 경로(직선)가 육지를 통과하지 않는 입자만 반환."""
        geometry = self._load()
        if geometry is None:
            return end_lons, end_lats
        from shapely.geometry import LineString, Point
        from shapely.prepared import prep

        prepared = prep(geometry)
        keep = np.asarray([
            not prepared.covers(Point(float(ex), float(ey)))
            and not prepared.intersects(
                LineString([(float(sx), float(sy)), (float(ex), float(ey))])
            )
            for sx, sy, ex, ey in zip(start_lons, start_lats, end_lons, end_lats, strict=True)
        ])
        return end_lons[keep], end_lats[keep]

    def clip_feature_collection(self, collection: dict) -> dict:
        geometry = self._load()
        if geometry is None:
            return collection
        from shapely.geometry import mapping, shape

        features = []
        for feature in collection["features"]:
            clipped = shape(feature["geometry"]).difference(geometry)
            if clipped.is_empty:
                continue
            features.append({**feature, "geometry": mapping(clipped)})
        # fallback: if all clipped to empty (e.g., tiny zone fully inside island polygon),
        # return original unclipped collection rather than empty FeatureCollection
        return {"type": "FeatureCollection", "features": features} if features else collection
