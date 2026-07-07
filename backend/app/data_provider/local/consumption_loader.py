"""
일별 행정동 시간/업종 소비매출 월별 일평균.csv 로더 (부산 전체, 36개월).

foot_traffic_loader와 동일하게 최신월 스냅샷만 사용한다.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.schemas import ConsumptionByCategory, ConsumptionByHour

_DATA_ROOT = Path(__file__).resolve().parents[4]
_HOUR_PATH = _DATA_ROOT / "일별 행정동 시간 소비매출 월별 일평균.csv"
_CATEGORY_PATH = _DATA_ROOT / "일별 행정동 업종 소비매출 월별 일평균.csv"


@lru_cache
def get_consumption_by_hour_latest_month() -> pd.DataFrame:
    df = pd.read_csv(_HOUR_PATH, encoding="utf-8")
    latest = df["기준년월"].max()
    return df[df["기준년월"] == latest].copy()


@lru_cache
def get_consumption_by_category_latest_month() -> pd.DataFrame:
    df = pd.read_csv(_CATEGORY_PATH, encoding="utf-8")
    latest = df["기준년월"].max()
    return df[df["기준년월"] == latest].copy()


def get_consumption_by_hour_for_dong(행정동코드: str) -> list[ConsumptionByHour]:
    df = get_consumption_by_hour_latest_month()
    sub = df[df["행정동코드"] == int(행정동코드)].sort_values("시간대")
    return [
        ConsumptionByHour(
            시간대=row["시간대"], 평균이용금액=int(row["평균이용금액"]), 평균이용건수=int(row["평균이용건수"])
        )
        for _, row in sub.iterrows()
    ]


def get_consumption_by_category_for_dong(행정동코드: str) -> list[ConsumptionByCategory]:
    df = get_consumption_by_category_latest_month()
    sub = df[df["행정동코드"] == int(행정동코드)]
    return [
        ConsumptionByCategory(
            업종대분류=row["업종대분류"], 평균이용금액=int(row["평균이용금액"]), 평균이용건수=int(row["평균이용건수"])
        )
        for _, row in sub.iterrows()
    ]
