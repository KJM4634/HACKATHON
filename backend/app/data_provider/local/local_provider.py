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
    FOOD_SUBCATEGORIES,
    FOOD_SUBCATEGORY_TO_SANGGABU_JUNGBUNLYU,
    RESTAURANT_UPTAE_EXCLUDE_FOR_OTHER,
    SANGGABU_FOOD_JUNGBUNLYU_EXCLUDE_FOR_OTHER,
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
_MIN_CLOSURE_SAMPLE = 5  # 표본이 이보다 적으면 폐업률이 노이즈에 가까워 신뢰할 수 없음 (조사 결과 기준)


def _to_sanggabu_code(region_id: str) -> int:
    """10자리 행정동코드(생활인구/소비매출 기준) -> 8자리(상가정보/일반음식점 기준)."""
    return int(region_id) // 100


def _to_region_id(sanggabu_code) -> str:
    return str(int(sanggabu_code) * 100)


@lru_cache
def _empty_sanggabu() -> pd.DataFrame:
    return get_sanggabu_busan().iloc[0:0]


@lru_cache
def _sanggabu_grouped_by_dong_for_keyword(keyword: str) -> dict:
    """get_competitors()가 매 지역 요청마다 13만 행 전체에 str.contains를 다시 돌리던 것
    (206개 행정동 x 매 요청)을 막기 위해, 키워드별로 한 번만 필터링 + groupby해서 캐시한다
    (_closure_stats_by_dong_and_uptae와 같은 패턴). 카페/편의점/미용실 3종류뿐이라 캐시
    3개면 끝(음식점 서브카테고리는 아래 _sanggabu_grouped_by_dong_for_jungbunlyu 참고)."""
    sanggabu = get_sanggabu_busan()
    matched = sanggabu[sanggabu["표준산업분류명"].str.contains(keyword, na=False)]
    # dict(matched.groupby(...))는 안 됨 — DataFrameGroupBy에 dict-like로 오인되는
    # .keys 속성(그루핑 키 스펙, 문자열)이 있어 "'str' object is not callable"로 터진다
    return {code: group for code, group in matched.groupby("행정동코드")}


@lru_cache
def _sanggabu_grouped_by_dong_for_jungbunlyu(jungbunlyu: str) -> dict:
    """음식점 서브카테고리(한식/중식/분식) 경쟁업체수 — 상권업종중분류명 정확매칭 버전."""
    sanggabu = get_sanggabu_busan()
    matched = sanggabu[sanggabu["상권업종중분류명"] == jungbunlyu]
    return {code: group for code, group in matched.groupby("행정동코드")}


@lru_cache
def _sanggabu_grouped_by_dong_for_other_food() -> dict:
    """'기타음식점' 경쟁업체수 = 음식 대분류 중 한식/중식/기타간이/비알코올(카페)을 뺀 나머지
    (주점·일식·서양식·구내식당뷔페·동남아시아 등)."""
    sanggabu = get_sanggabu_busan()
    food = sanggabu[sanggabu["상권업종대분류명"] == "음식"]
    matched = food[~food["상권업종중분류명"].isin(SANGGABU_FOOD_JUNGBUNLYU_EXCLUDE_FOR_OTHER)]
    return {code: group for code, group in matched.groupby("행정동코드")}


@lru_cache
def _closure_stats_by_dong_and_uptae() -> pd.DataFrame:
    """(행정동코드,업태구분명) -> 영업중/최근폐업/최근개업 집계.

    get_closure_stats()가 행정동 하나당 13만 행 전체를 다시 스캔하던 것(206개
    행정동 x 매 요청마다 반복 -> /api/scores?category=음식점이 ~10초 걸림)을
    막기 위해 전체를 한 번만 groupby해서 캐시한다(get_restaurants_with_admin_dong의
    KDTree 최적화와 같은 패턴)."""
    df = get_restaurants_with_admin_dong()
    with_dong = df[df["행정동코드"].notna()].copy()
    with_dong["행정동코드"] = with_dong["행정동코드"].astype("int64")

    cutoff = pd.Timestamp.now() - pd.Timedelta(days=_RECENT_CLOSURE_WINDOW_DAYS)
    폐업일자 = pd.to_datetime(with_dong["폐업일자"], errors="coerce")
    인허가일자 = pd.to_datetime(with_dong["인허가일자"], errors="coerce")

    with_dong["_active"] = with_dong["영업상태명"] == "영업/정상"
    with_dong["_closed_recent"] = (with_dong["영업상태명"] == "폐업") & (폐업일자 >= cutoff)
    with_dong["_opened_recent"] = 인허가일자 >= cutoff

    return with_dong.groupby(["행정동코드", "업태구분명"])[["_active", "_closed_recent", "_opened_recent"]].sum()


@lru_cache
def _closure_stats_other_food_by_dong() -> pd.DataFrame:
    """'기타음식점' 폐업률 = 한식/중국식/분식을 뺀 나머지 업태(호프/통닭·숯불구이·횟집·
    주점·일식·경양식 등) 전부를 행정동별로 합산. _closure_stats_by_dong_and_uptae처럼
    (행정동코드,업태구분명) 개별 조회가 아니라 행정동코드 하나로 합쳐야 해서 별도 캐시."""
    df = get_restaurants_with_admin_dong()
    with_dong = df[df["행정동코드"].notna() & ~df["업태구분명"].isin(RESTAURANT_UPTAE_EXCLUDE_FOR_OTHER)].copy()
    with_dong["행정동코드"] = with_dong["행정동코드"].astype("int64")

    cutoff = pd.Timestamp.now() - pd.Timedelta(days=_RECENT_CLOSURE_WINDOW_DAYS)
    폐업일자 = pd.to_datetime(with_dong["폐업일자"], errors="coerce")
    인허가일자 = pd.to_datetime(with_dong["인허가일자"], errors="coerce")

    with_dong["_active"] = with_dong["영업상태명"] == "영업/정상"
    with_dong["_closed_recent"] = (with_dong["영업상태명"] == "폐업") & (폐업일자 >= cutoff)
    with_dong["_opened_recent"] = 인허가일자 >= cutoff

    return with_dong.groupby("행정동코드")[["_active", "_closed_recent", "_opened_recent"]].sum()


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

        if category in FOOD_SUBCATEGORIES:
            jungbunlyu = FOOD_SUBCATEGORY_TO_SANGGABU_JUNGBUNLYU.get(category)
            groups = (
                _sanggabu_grouped_by_dong_for_other_food()
                if jungbunlyu is None
                else _sanggabu_grouped_by_dong_for_jungbunlyu(jungbunlyu)
            )
        else:
            keyword = CATEGORY_TO_SANGGABU_KEYWORD.get(category, category)
            groups = _sanggabu_grouped_by_dong_for_keyword(keyword)

        matched = groups.get(code8, _empty_sanggabu())

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
        code8 = _to_sanggabu_code(region_id)

        if category == "기타음식점":
            try:
                active, closed_recent, opened_recent = _closure_stats_other_food_by_dong().loc[code8]
            except KeyError:
                active, closed_recent, opened_recent = 0, 0, 0
            label = "기타음식점(호프/통닭·숯불구이·횟집·주점·일식·경양식 등)"
        else:
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
            try:
                active, closed_recent, opened_recent = _closure_stats_by_dong_and_uptae().loc[(code8, uptae)]
            except KeyError:
                active, closed_recent, opened_recent = 0, 0, 0
            label = uptae

        denom = active + closed_recent
        # 표본이 너무 적으면(조사 결과 기준 5건 미만) 폐업률이 노이즈에 가까워, 카페/편의점/
        # 미용실과 동일하게 "데이터 없음"으로 처리한다 — 다만 원자료 건수는 그대로 남겨서
        # scoring.py가 "왜" 안내 문구를 다르게 쓸지(구조적 부재 vs 표본 부족) 판단할 수 있게 한다.
        if denom < _MIN_CLOSURE_SAMPLE:
            return ClosureStats(
                업태구분명=label,
                영업중_점포수=int(active),
                최근1년_신규개업_수=int(opened_recent),
                최근1년_폐업_수=int(closed_recent),
                폐업률=0.0,
                data_available=False,
            )

        rate = round(closed_recent / denom * 100, 1)
        return ClosureStats(
            업태구분명=label,
            영업중_점포수=int(active),
            최근1년_신규개업_수=int(opened_recent),
            최근1년_폐업_수=int(closed_recent),
            폐업률=rate,
            data_available=True,
        )
