"""
DRIFT - land_utils.py  (목포 해역 전용)
==========================================
Monte Carlo 입자 육지 stranding 판정 + 폴리곤 해양 클리핑.

데이터: land_mokpo_v6.geojson (남한 시도 행정경계 기반, 다도해 섬 포함)

사용법:
    from land_utils import LandChecker

    checker = LandChecker()
    sea, stranded = checker.filter_particles(particles)
    clipped_zones = checker.clip_search_zones(search_zones)
"""

import os
from functools import lru_cache
from shapely.geometry import Point, shape, mapping
from shapely.ops import unary_union
import geopandas as gpd

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_LAND_FILE = os.path.join(_BASE_DIR, "land_mokpo_v6.geojson")


class LandChecker:
    def __init__(self):
        self._land = self._load(_LAND_FILE)

    @staticmethod
    @lru_cache(maxsize=1)
    def _load(path: str):
        gdf = gpd.read_file(path)
        return unary_union(gdf.geometry)

    def is_on_land(self, lat: float, lon: float) -> bool:
        """True = 육지/섬(stranding), False = 해양(유효)"""
        return self._land.contains(Point(lon, lat))

    def filter_particles(self, particles: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        Monte Carlo 입자 분류.
        particles: [{"lat": float, "lon": float, ...}, ...]
        Returns: (sea_particles, stranded_particles)
        """
        sea, stranded = [], []
        for p in particles:
            (stranded if self.is_on_land(p["lat"], p["lon"]) else sea).append(p)
        return sea, stranded

    def clip_polygon(self, polygon_geojson: dict) -> dict | None:
        """GeoJSON geometry에서 육지 제거. 전부 육지면 None 반환."""
        clipped = shape(polygon_geojson).difference(self._land)
        return None if clipped.is_empty else mapping(clipped)

    def clip_search_zones(self, zones: list[dict]) -> list[dict]:
        """
        DRIFT search_zones 전체 육지 클리핑.
        zones: [{"rank":1, "probability":60, "geometry":{...GeoJSON...}}, ...]
        """
        result = []
        for zone in zones:
            geom = self.clip_polygon(zone["geometry"])
            if geom:
                result.append({**zone, "geometry": geom})
        return result


if __name__ == "__main__":
    import random, time

    checker = LandChecker()

    print("=== 목포 해역 LandChecker 검증 ===\n")
    tests = [
        (34.815, 126.367, False, "목포북항북측 관측소 — 해상"),
        (34.800, 126.400, True,  "목포 시내 — 육지"),
        (34.500, 125.500, False, "흑산도 서쪽 외해"),
        (34.200, 126.000, False, "완도 남쪽 외해"),
    ]
    for lat, lon, exp, desc in tests:
        r = checker.is_on_land(lat, lon)
        print(f"  {'✅' if r==exp else '❌'} ({lat}, {lon}) → {'육지' if r else '해양'} | {desc}")

    print("\n=== 성능: 1000입자 필터 ===")
    random.seed(42)
    particles = [
        {"lat": random.uniform(33.5, 35.5), "lon": random.uniform(125.0, 127.5), "id": i}
        for i in range(1000)
    ]
    t0 = time.time()
    sea, land = checker.filter_particles(particles)
    print(f"  처리 시간: {(time.time()-t0)*1000:.1f}ms")
    print(f"  해양: {len(sea)}개, 육지(stranding): {len(land)}개")
