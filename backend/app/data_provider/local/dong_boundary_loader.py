"""
행정동 경계 GeoJSON(frontend/public/busan_dong_boundaries.geojson) 로더.

지도 렌더링용으로 프론트가 이미 쓰는 그 파일을 백엔드도 그대로 읽는다 — 별도
경계 데이터를 새로 만들지 않고, 격자(app/grid.py)를 만들 때 필요한 면적/
bbox/포함여부 판정에만 쓴다. adm_cd2 속성이 이미 10자리 행정동코드라
RegionInfo.region_id와 그대로 맞아떨어진다(변환 불필요).
"""

from functools import lru_cache
from pathlib import Path

from pyproj import Geod

# backend/app/data_provider/local/dong_boundary_loader.py -> 프로젝트 루트
_DATA_ROOT = Path(__file__).resolve().parents[4]
_GEOJSON_PATH = _DATA_ROOT / "frontend" / "public" / "busan_dong_boundaries.geojson"

_GEOD = Geod(ellps="WGS84")


@lru_cache
def get_dong_boundaries() -> dict[str, dict]:
    """region_id(10자리 행정동코드) -> GeoJSON feature. 프로세스당 1회 로드."""
    import json

    with _GEOJSON_PATH.open(encoding="utf-8") as f:
        geojson = json.load(f)
    return {feat["properties"]["adm_cd2"]: feat for feat in geojson["features"]}


def _rings(feature: dict) -> list[list[list[float]]]:
    """MultiPolygon/Polygon geometry를 (외곽선, 구멍1, 구멍2...) 리스트의 리스트로 통일."""
    geom = feature["geometry"]
    return geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]


def _ring_area(ring: list[list[float]]) -> float:
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    area, _ = _GEOD.polygon_area_perimeter(lons, lats)
    return abs(area)


def polygon_area_m2(feature: dict) -> float:
    """지오데식(구면) 면적, m^2. 격자 크기 선택(app/grid.py)에 쓴다."""
    total = 0.0
    for polygon in _rings(feature):
        exterior = polygon[0]
        area = _ring_area(exterior)
        for hole in polygon[1:]:
            area -= _ring_area(hole)
        total += area
    return total


def polygon_bbox(feature: dict) -> tuple[float, float, float, float]:
    """(min_lon, max_lon, min_lat, max_lat)."""
    min_lon = min_lat = float("inf")
    max_lon = max_lat = float("-inf")
    for polygon in _rings(feature):
        for lon, lat in polygon[0]:  # 외곽선만으로 충분 (구멍은 항상 외곽선 안에 있음)
            min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)
            min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)
    return min_lon, max_lon, min_lat, max_lat


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """표준 ray-casting 알고리즘(짝수/홀수 규칙)."""
    inside = False
    n = len(ring)
    x1, y1 = ring[0]
    for i in range(1, n + 1):
        x2, y2 = ring[i % n]
        if (y1 > lat) != (y2 > lat):
            x_intersect = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_intersect:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def point_in_feature(lon: float, lat: float, feature: dict) -> bool:
    """이 점이 (구멍 제외) 폴리곤 내부에 있는지. 격자 셀 중심점이 실제 행정동
    모양 안에 있는 것만 골라 렌더링하는 데 쓴다(bbox 그대로 쓰면 이웃 동/바다까지
    사각형으로 덮여 모양이 어색해짐)."""
    for polygon in _rings(feature):
        exterior = polygon[0]
        if not _point_in_ring(lon, lat, exterior):
            continue
        if any(_point_in_ring(lon, lat, hole) for hole in polygon[1:]):
            continue
        return True
    return False
