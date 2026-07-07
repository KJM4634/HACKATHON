"""
현재는 MockDataProvider만 존재. 4단계에서 LocalDataProvider를 추가하면
get_data_provider()의 반환값만 바꿔서 상위 로직(스코어링/LLM) 무변경으로 교체한다.
"""

from functools import lru_cache

from app.data_provider.base import DataProvider
from app.data_provider.mock_provider import MockDataProvider


@lru_cache
def get_data_provider() -> DataProvider:
    return MockDataProvider()
