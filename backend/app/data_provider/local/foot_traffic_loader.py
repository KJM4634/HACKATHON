"""
일별 행정동 시간 생활인구 월별 일평균.csv 로더 (부산 전체 206개 행정동, 36개월).

스코어링/리포트는 "현재 상태"를 봐야 하므로 최신월(기준년월 최댓값) 스냅샷만 쓴다.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.schemas import FootTrafficByHour

_DATA_ROOT = Path(__file__).resolve().parents[4]
_PATH = _DATA_ROOT / "일별 행정동 시간 생활인구 월별 일평균.csv"


@lru_cache
def get_foot_traffic_latest_month() -> pd.DataFrame:
    """행정동코드/행정동명/시간대/평균주거인구수/평균직장인구수/평균방문인구수, 최신월만."""
    df = pd.read_csv(_PATH, encoding="utf-8")
    latest = df["기준년월"].max()
    return df[df["기준년월"] == latest].copy()


def get_foot_traffic_for_dong(행정동코드: str) -> list[FootTrafficByHour]:
    df = get_foot_traffic_latest_month()
    sub = df[df["행정동코드"] == int(행정동코드)].sort_values("시간대")
    return [
        FootTrafficByHour(
            시간대=row["시간대"],
            평균주거인구수=int(row["평균주거인구수"]),
            평균직장인구수=int(row["평균직장인구수"]),
            평균방문인구수=int(row["평균방문인구수"]),
        )
        for _, row in sub.iterrows()
    ]
