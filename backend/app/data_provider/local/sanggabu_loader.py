"""
소상공인시장진흥공단 상가(상권)정보 로더 (현재는 부산만).

LocalDataProvider의 get_competitors() 구현과, restaurant_loader의 법정동->행정동
배정(dong_mapper)이 공통으로 참조할 원본 데이터라 별도 모듈로 분리했다.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

_DATA_ROOT = Path(__file__).resolve().parents[4]

_BUSAN_PATH = (
    _DATA_ROOT
    / "소상공인시장진흥공단_상가(상권)정보"
    / "소상공인시장진흥공단_상가(상권)정보_부산_202603.csv"
)


@lru_cache
def get_sanggabu_busan() -> pd.DataFrame:
    """부산 상가(상권)정보. 프로세스당 1회 로드 후 캐시.

    상권업종중분류명 원본 값에 트레일링 공백이 섞여 있어("비알코올 " 등) 정확매칭이
    실패하는 경우가 있었다 — 음식점 서브카테고리 필터링에서 정확매칭을 쓰므로 로드
    시점에 한 번만 정리한다."""
    df = pd.read_csv(_BUSAN_PATH, encoding="utf-8", low_memory=False)
    df["상권업종중분류명"] = df["상권업종중분류명"].str.strip()
    return df
