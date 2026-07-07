"""
DataProvider 인터페이스 (PRD 4장 2-Track 데이터 전략).

상위 로직(스코어링 엔진, LLM 리포트 생성)은 이 인터페이스만 알고 있으면 되고,
데이터가 MockDataProvider / LocalDataProvider(4단계) / ApiDataProvider(필요시) 중
무엇에서 오는지는 신경 쓰지 않는다.

각 메서드는 data_inventory.md에서 확인한 실제 데이터셋 하나에 1:1로 대응한다.
그래야 4단계에서 LocalDataProvider를 구현할 때 메서드 하나당 "CSV 하나 읽어서 가공"으로
바로 옮길 수 있다.
"""

from abc import ABC, abstractmethod

from app.schemas import (
    ClosureStats,
    CompetitorSummary,
    ConsumptionByCategory,
    ConsumptionByHour,
    FootTrafficByHour,
    MarketData,
    PopulationStats,
    RegionInfo,
)


class DataProvider(ABC):
    @abstractmethod
    def list_regions(self) -> list[RegionInfo]:
        """서비스가 다루는 전체 지역 목록. (4단계: 상가정보의 행정동명 유니크 목록으로 대체)"""

    @abstractmethod
    def get_region_info(self, region_id: str) -> RegionInfo:
        """지역 기본 정보. (4단계: 상가정보 CSV의 행정동코드/명, 좌표 평균)"""

    @abstractmethod
    def get_population(self, region_id: str) -> PopulationStats:
        """배후 인구. (4단계: 인구세대현황 CSV, 시군구 단위 — 행정동 -> 시군구 매핑 필요)"""

    @abstractmethod
    def get_foot_traffic(self, region_id: str) -> list[FootTrafficByHour]:
        """시간대별 유동인구. (4단계: 일별 행정동 시간 생활인구 월별 일평균.csv)"""

    @abstractmethod
    def get_consumption_by_hour(self, region_id: str) -> list[ConsumptionByHour]:
        """시간대별 소비매출. (4단계: 일별 행정동 시간 소비매출 월별 일평균.csv)"""

    @abstractmethod
    def get_consumption_by_category(self, region_id: str) -> list[ConsumptionByCategory]:
        """업종별 소비매출. (4단계: 일별 행정동 업종 소비매출 월별 일평균.csv)"""

    @abstractmethod
    def get_competitors(self, region_id: str, category: str) -> CompetitorSummary:
        """동일업종 경쟁업체 밀집도. (4단계: 상가(상권)정보 CSV, 상권업종/표준산업분류로 필터)"""

    @abstractmethod
    def get_closure_stats(self, region_id: str, category: str) -> ClosureStats:
        """개폐업 현황·폐업률. (4단계: 일반음식점표준데이터 CSV, 인허가일자/폐업일자 집계)"""

    def get_market_data(self, region_id: str, category: str) -> MarketData:
        """위 메서드들을 조합한 기본 구현. 서브클래스가 그대로 상속해 쓸 수 있다."""
        return MarketData(
            region=self.get_region_info(region_id),
            population=self.get_population(region_id),
            foot_traffic=self.get_foot_traffic(region_id),
            consumption_by_hour=self.get_consumption_by_hour(region_id),
            consumption_by_category=self.get_consumption_by_category(region_id),
            competitors=self.get_competitors(region_id, category),
            closure_stats=self.get_closure_stats(region_id, category),
        )
