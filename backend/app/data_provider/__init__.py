"""
4단계: LocalDataProvider(실제 부산 데이터)를 기본으로 쓴다.
MockDataProvider는 PRD 4장 fallback 체인의 마지막 단계로 계속 남겨둔다
(예: 원본 CSV가 없는 환경, 데모 사고 시 즉시 전환용).
"""

from functools import lru_cache

from app.data_provider.base import DataProvider
from app.data_provider.local.local_provider import LocalDataProvider


@lru_cache
def get_data_provider() -> DataProvider:
    return LocalDataProvider()
