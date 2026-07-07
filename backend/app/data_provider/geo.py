"""
좌표계 변환 유틸리티.

일반음식점표준데이터의 좌표정보(X)/(Y)는 EPSG:5174(Korean 1985 / Modified Central
Belt, Bessel) 평면좌표이고, 상가(상권)정보의 경도/위도는 EPSG:4326(WGS84)이다.
두 데이터를 같은 지도 위에 올리려면 하나의 좌표계로 통일해야 한다.

EPSG:5174로 확정한 근거 (2026-07-08 검증):
부산 중구 부평동3가 79-12 소재 일반음식점 좌표(X=384477.79, Y=180066.61)를
EPSG:5174/2097/5181 세 후보로 각각 WGS84 변환해, 같은 지번 블록(부평동3가
79-1~79-19)의 상가(상권)정보 실측 WGS84 좌표와 비교했다. EPSG:5174 변환값만
20~30m 이내로 일치했고, 2097/5181은 90~300m씩 벗어났다.
(회귀 테스트: tests/test_geo.py)

pyproj.Transformer 생성 비용이 크므로 모듈 레벨에서 한 번만 만들어 재사용한다.
"""

import logging

import numpy as np
import pandas as pd
from pyproj import Transformer

logger = logging.getLogger(__name__)

_TM5174_TO_WGS84 = Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)

# 부울경 대략적인 위경도 범위. 변환 결과가 이 범위를 벗어나면 좌표계/단위를
# 잘못 짚었을 가능성이 크므로 transform_tm5174_to_wgs84()에서 경고를 남긴다.
BUSAN_ULSAN_GYEONGNAM_BOUNDS = {"lon": (127.5, 129.6), "lat": (34.5, 36.0)}


def transform_tm5174_to_wgs84(x: pd.Series, y: pd.Series) -> tuple[pd.Series, pd.Series]:
    """EPSG:5174 평면좌표(x, y) -> (경도, 위도). NaN 입력은 NaN으로 유지."""
    x = pd.to_numeric(x, errors="coerce")
    y = pd.to_numeric(y, errors="coerce")

    valid = x.notna() & y.notna()
    lon = pd.Series(np.nan, index=x.index, dtype="float64")
    lat = pd.Series(np.nan, index=x.index, dtype="float64")

    if valid.any():
        lon_vals, lat_vals = _TM5174_TO_WGS84.transform(x[valid].to_numpy(), y[valid].to_numpy())
        lon[valid] = lon_vals
        lat[valid] = lat_vals

    lon_min, lon_max = BUSAN_ULSAN_GYEONGNAM_BOUNDS["lon"]
    lat_min, lat_max = BUSAN_ULSAN_GYEONGNAM_BOUNDS["lat"]
    out_of_bounds = valid & ~(lon.between(lon_min, lon_max) & lat.between(lat_min, lat_max))
    if out_of_bounds.any():
        logger.warning(
            "TM5174->WGS84 변환 결과 %d건이 부울경 범위를 벗어남 — 좌표계/단위를 다시 확인하세요.",
            int(out_of_bounds.sum()),
        )

    return lon, lat
