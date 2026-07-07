"""
일반음식점표준데이터 로더 (부산/울산/경남).

3개 CSV를 읽어 하나로 합치고, TM(EPSG:5174) 좌표를 WGS84 경도/위도로 변환해
상가(상권)정보와 동일한 좌표계로 맞춘다.

변환은 요청마다 다시 하지 않고 프로세스당 한 번만 계산해 메모리에 캐시한다
(get_restaurants_wgs84에 @lru_cache). LocalDataProvider(4단계)가 이 함수를
불러다 쓸 예정이다.

get_restaurants_with_admin_dong()은 여기에 행정동코드/행정동명을 추가로
배정한다. 현재는 부산만 지원(PRD 데모 범위가 부산 중심으로 확정됐기 때문) —
경남/울산은 행정동 컬럼이 비워진 채로 나오고, 그 지역이 스코프에 들어올 때
같은 방식으로 매퍼를 하나 더 만들면 된다.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.data_provider.geo import transform_tm5174_to_wgs84
from app.data_provider.local.dong_mapper import LegalToAdminDongMapper, parse_sigungu_and_legal_dong
from app.data_provider.local.sanggabu_loader import get_sanggabu_busan

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


def _assign_admin_dong_busan(row: pd.Series, mapper: LegalToAdminDongMapper) -> pd.Series:
    parsed = parse_sigungu_and_legal_dong(row["지번주소"], mapper)
    if parsed is None:
        parsed = parse_sigungu_and_legal_dong(row["도로명주소"], mapper)
    if parsed is None:
        return pd.Series({"행정동코드": None, "행정동명": None})

    sigungu, legal_dong = parsed
    admin = mapper.assign(sigungu, legal_dong, row["경도"], row["위도"])
    if admin is None:
        return pd.Series({"행정동코드": None, "행정동명": None})
    return pd.Series({"행정동코드": admin.행정동코드, "행정동명": admin.행정동명})


@lru_cache
def get_restaurants_with_admin_dong() -> pd.DataFrame:
    """get_restaurants_wgs84() + 행정동코드/행정동명 (현재는 부산만 배정)."""
    df = get_restaurants_wgs84().copy()
    df["행정동코드"] = None
    df["행정동명"] = None

    busan_mask = df["시도명"] == "부산광역시"
    mapper = LegalToAdminDongMapper(get_sanggabu_busan())

    assigned = df.loc[busan_mask].apply(_assign_admin_dong_busan, axis=1, mapper=mapper)
    df.loc[busan_mask, ["행정동코드", "행정동명"]] = assigned[["행정동코드", "행정동명"]]

    return df
