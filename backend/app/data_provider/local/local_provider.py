"""
LocalDataProvider: 실제 부산 데이터로 DataProvider 인터페이스를 구현.

region_id는 10자리 행정동코드 문자열이다(생활인구/소비매출 CSV와 동일 형식).
상가(상권)정보·일반음식점표준데이터는 8자리 행정동코드를 쓰므로
10자리 = 8자리 * 100 관계로 서로 변환한다(dong_mapper.py에서 이미 검증한 관계).

MockDataProvider의 프리셋 region_id("seomyeon" 등)와는 값이 다르다 — Local은
206개 행정동 전체를 다루므로 사람이 읽을 수 있는 별칭 대신 행정동코드를
그대로 region_id로 쓴다.
"""

from functools import lru_cache

import pandas as pd

from app.data_provider.base import DataProvider
from app.data_provider.local.category_mapping import (
    CATEGORY_TO_RESTAURANT_UPTAE,
    CATEGORY_TO_SANGGABU_KEYWORD,
)
from app.data_provider.local.consumption_loader import (
    get_consumption_by_category_for_dong,
    get_consumption_by_hour_for_dong,
)
from app.data_provider.local.foot_traffic_loader import get_foot_traffic_for_dong
from app.data_provider.local.population_loader import get_population_by_gu
from app.data_provider.local.restaurant_loader import get_restaurants_with_admin_dong
from app.data_provider.local.sanggabu_loader import get_sanggabu_busan
from app.schemas import (
    ClosureStats,
    CompetitorBusiness,
    CompetitorSummary,
    ConsumptionByCategory,
    ConsumptionByHour,
    FootTrafficByHour,
    PopulationStats,
    RegionInfo,
)

_RECENT_CLOSURE_WINDOW_DAYS = 365


def _to_sanggabu_code(region_id: str) -> int:
    """10자리 행정동코드(생활인구/소비매출 기준) -> 8자리(상가정보/일반음식점 기준)."""
    return int(region_id) // 100


def _to_region_id(sanggabu_code) -> str:
    return str(int(sanggabu_code) * 100)


@lru_cache
def _region_lookup() -> pd.DataFrame:
    """행정동코드(8자리) -> 행정동명/시군구명/중심좌표."""
    sanggabu = get_sanggabu_busan()
    return (
        sanggabu.groupby("행정동코드")
        .agg(
            행정동명=("행정동명", "first"),
            시군구명=("시군구명", "first"),
            경도=("경도", "mean"),
            위도=("위도", "mean"),
        )
        .reset_index()
    )


class LocalDataProvider(DataProvider):
    def list_regions(self) -> list[RegionInfo]:
        lookup = _region_lookup()
        return [self._row_to_region_info(row) for _, row in lookup.iterrows()]

    def get_region_info(self, region_id: str) -> RegionInfo:
        code8 = _to_sanggabu_code(region_id)
        lookup = _region_lookup()
        matched = lookup[lookup["행정동코드"] == code8]
        if matched.empty:
            raise ValueError(f"알 수 없는 region_id: {region_id}")
        return self._row_to_region_info(matched.iloc[0])

    @staticmethod
    def _row_to_region_info(row) -> RegionInfo:
        region_id = _to_region_id(row["행정동코드"])
        return RegionInfo(
            region_id=region_id,
            행정동코드=region_id,
            행정동명=f"{row['시군구명']} {row['행정동명']}",
            시도명="부산광역시",
            시군구명=row["시군구명"],
            위도=row["위도"],
            경도=row["경도"],
        )

    def get_population(self, region_id: str) -> PopulationStats:
        region = self.get_region_info(region_id)
        stats = get_population_by_gu().get(region.시군구명)
        if stats is None:
            raise ValueError(f"인구 데이터 없음: {region.시군구명}")
        return stats

    def get_foot_traffic(self, region_id: str) -> list[FootTrafficByHour]:
        return get_foot_traffic_for_dong(region_id)

    def get_consumption_by_hour(self, region_id: str) -> list[ConsumptionByHour]:
        return get_consumption_by_hour_for_dong(region_id)

    def get_consumption_by_category(self, region_id: str) -> list[ConsumptionByCategory]:
        return get_consumption_by_category_for_dong(region_id)

    def get_competitors(self, region_id: str, category: str) -> CompetitorSummary:
        code8 = _to_sanggabu_code(region_id)
        keyword = CATEGORY_TO_SANGGABU_KEYWORD.get(category, category)

        sanggabu = get_sanggabu_busan()
        matched = sanggabu[
            (sanggabu["행정동코드"] == code8) & sanggabu["표준산업분류명"].str.contains(keyword, na=False)
        ]

        sample = [
            CompetitorBusiness(
                상호명=row["상호명"],
                상권업종대분류명=row["상권업종대분류명"],
                상권업종중분류명=row["상권업종중분류명"],
                상권업종소분류명=row["상권업종소분류명"] if pd.notna(row["상권업종소분류명"]) else None,
                표준산업분류명=row["표준산업분류명"],
                경도=row["경도"],
                위도=row["위도"],
                도로명주소=row["도로명주소"] if pd.notna(row["도로명주소"]) else None,
            )
            for _, row in matched.head(20).iterrows()
        ]
        return CompetitorSummary(target_category=category, total_count=len(matched), sample=sample)

    def get_closure_stats(self, region_id: str, category: str) -> ClosureStats:
        uptae = CATEGORY_TO_RESTAURANT_UPTAE.get(category)
        if uptae is None:
            return ClosureStats(
                업태구분명=category,
                영업중_점포수=0,
                최근1년_신규개업_수=0,
                최근1년_폐업_수=0,
                폐업률=0.0,
                data_available=False,
            )

        code8 = _to_sanggabu_code(region_id)
        df = get_restaurants_with_admin_dong()

        with_dong = df[df["행정동코드"].notna()]
        sub = with_dong[
            (with_dong["행정동코드"].astype("int64") == code8) & (with_dong["업태구분명"] == uptae)
        ]

        active = int((sub["영업상태명"] == "영업/정상").sum())
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=_RECENT_CLOSURE_WINDOW_DAYS)
        폐업일자 = pd.to_datetime(sub["폐업일자"], errors="coerce")
        인허가일자 = pd.to_datetime(sub["인허가일자"], errors="coerce")
        closed_recent = int(((sub["영업상태명"] == "폐업") & (폐업일자 >= cutoff)).sum())
        opened_recent = int((인허가일자 >= cutoff).sum())

        denom = active + closed_recent
        rate = round(closed_recent / denom * 100, 1) if denom > 0 else 0.0

        return ClosureStats(
            업태구분명=uptae,
            영업중_점포수=active,
            최근1년_신규개업_수=opened_recent,
            최근1년_폐업_수=closed_recent,
            폐업률=rate,
            data_available=True,
        )
