"""
일반음식점표준데이터 로더 (부산/울산/경남).

3개 CSV를 읽어 하나로 합치고, TM(EPSG:5174) 좌표를 WGS84 경도/위도로 변환해
상가(상권)정보와 동일한 좌표계로 맞춘다.

변환은 요청마다 다시 하지 않고 프로세스당 한 번만 계산해 메모리에 캐시한다
(get_restaurants_wgs84에 @lru_cache). LocalDataProvider(4단계)가 이 함수를
불러다 쓸 예정이다.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.data_provider.geo import transform_tm5174_to_wgs84

# backend/app/data_provider/local/restaurant_loader.py -> 프로젝트 루트
_DATA_ROOT = Path(__file__).resolve().parents[4]

_SOURCE_FILES: dict[str, Path] = {
    "부산광역시": _DATA_ROOT / "부울경_일반음식점표준데이터" / "식품_일반음식점_부산광역시.csv",
    "울산광역시": _DATA_ROOT / "부울경_일반음식점표준데이터" / "식품_일반음식점_울산광역시.csv",
    "경상남도": _DATA_ROOT / "부울경_일반음식점표준데이터" / "식품_일반음식점_경상남도.csv",
}


def _load_one(시도명: str, path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="cp949", low_memory=False)
    df["시도명"] = 시도명
    return df


@lru_cache
def get_restaurants_wgs84() -> pd.DataFrame:
    """부울경 일반음식점표준데이터 + WGS84 경도/위도 컬럼. 프로세스당 1회 계산 후 캐시."""
    frames = [_load_one(name, path) for name, path in _SOURCE_FILES.items()]
    df = pd.concat(frames, ignore_index=True)

    df["경도"], df["위도"] = transform_tm5174_to_wgs84(df["좌표정보(X)"], df["좌표정보(Y)"])
    return df
