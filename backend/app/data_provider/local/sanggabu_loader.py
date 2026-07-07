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
    """부산 상가(상권)정보. 프로세스당 1회 로드 후 캐시."""
    return pd.read_csv(_BUSAN_PATH, encoding="utf-8", low_memory=False)
