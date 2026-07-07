"""
행정동별_주민등록_인구_및_세대현황_부산.csv 로더.

이 파일은 이름과 달리 실제로는 시/군/구 단위 데이터다(data_inventory.md에서
확인). 행정동 단위 인구는 없으므로, LocalDataProvider는 이 구 단위 값을
소속된 모든 행정동에 그대로 적용하고 PopulationStats.is_gu_level_estimate=True로
표시한다.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.schemas import PopulationStats

_DATA_ROOT = Path(__file__).resolve().parents[4]
_PATH = (
    _DATA_ROOT
    / "부울경_행정동별_주민등록_인구_및_세대현황"
    / "행정동별_주민등록_인구_및_세대현황_부산.csv"
)

_YEAR = 2025


def _parse_gu_name(행정구역: str) -> str | None:
    """'부산광역시 부산광역시 중구 (2611000000)' -> '중구'. 시 전체 합계 행이면 None."""
    before_paren = 행정구역.split("(")[0].strip()
    tokens = before_paren.split()
    if len(tokens) < 2:
        return None  # 부산광역시 전체 합계 행
    return tokens[-1]


def _to_number(value: str, cast):
    return cast(str(value).replace(",", "").strip())


@lru_cache
def get_population_by_gu() -> dict[str, PopulationStats]:
    """구명 -> PopulationStats (2025년 기준, 구 단위)."""
    df = pd.read_csv(_PATH, encoding="cp949")

    result: dict[str, PopulationStats] = {}
    for _, row in df.iterrows():
        gu = _parse_gu_name(row["행정구역"])
        if gu is None:
            continue
        result[gu] = PopulationStats(
            기준연도=_YEAR,
            총인구수=_to_number(row[f"{_YEAR}년_총인구수"], int),
            세대수=_to_number(row[f"{_YEAR}년_세대수"], int),
            세대당_인구=_to_number(row[f"{_YEAR}년_세대당 인구"], float),
            남자_인구수=_to_number(row[f"{_YEAR}년_남자 인구수"], int),
            여자_인구수=_to_number(row[f"{_YEAR}년_여자 인구수"], int),
            is_gu_level_estimate=True,
        )
    return result
