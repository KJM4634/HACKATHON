"""
행정동 하나를 클릭했을 때만 그 동 안을 250m~1000m 격자로 잘라 보여주는 "격자
확대 모드" 계산 엔진.

기존 206개 행정동 파이프라인(DataProvider/scoring.py)은 전혀 건드리지 않는다 —
격자는 region_id를 재사용하지 않고 별도 계산 경로로 완전히 분리했다(설계
확정 시 이유: local_provider.py의 region_id는 여러 곳에서 정수 변환/딕셔너리
키로 쓰여서, 격자 합성 ID를 끼워 넣으면 회귀 위험이 생김).

스코어링 방식이 scoring.py(compute_score)와 다른 점 하나: 정규화 상/하한을
"부산 206개 행정동 전체 분포"가 아니라 "이 행정동 안 격자들끼리의 min~max"로
쓴다. 이유는 두 가지다.
1) 도시 전체 기준으로 정규화하면 격자 단위 값(경쟁업체 수가 한 자리인 경우가
   흔함)이 거의 항상 0점 근처로 눌려서, "이 동 안에서 어디가 더 낫다"는 비교가
   안 보이게 된다.
2) "격자 확대 모드"의 목적 자체가 부산 전체 순위가 아니라 "이 동 안의 상대적
   위치"라, 오히려 동네 안 상대비교가 이 기능의 취지에 더 맞는다.
   (그래서 격자 점수는 다른 동과 비교하면 안 됨 — GridCellDetailResponse.label에
   행정동명을 항상 같이 보여줘서 "이 동 안에서"라는 맥락을 잃지 않게 한다.)

인구/유동인구(배후수요) 근사: 조사 결과 채택한 B-2(POI 밀도 가중 배분) —
이 행정동에 있는 상가업소 전체(업종 무관, 개수만)의 격자별 분포로 행정동
단위 방문인구/구단위 인구를 셀에 나눠 배분한다. 경쟁업체수/폐업률은 원래도
좌표 데이터라 근사가 필요 없고 셀 안의 실제 값을 그대로 쓴다.
"""

import math
from dataclasses import dataclass, field

import pandas as pd

from app.alternatives import LOW_SCORE_THRESHOLD, find_alternatives
from app.data_provider.local.category_mapping import (
    CATEGORY_TO_RESTAURANT_UPTAE,
    CATEGORY_TO_SANGGABU_KEYWORD,
    FOOD_SUBCATEGORIES,
    FOOD_SUBCATEGORY_TO_SANGGABU_JUNGBUNLYU,
    RESTAURANT_UPTAE_EXCLUDE_FOR_OTHER,
    SANGGABU_FOOD_JUNGBUNLYU_EXCLUDE_FOR_OTHER,
)
from app.data_provider.local.consumption_loader import get_consumption_by_category_for_dong
from app.data_provider.local.dong_boundary_loader import (
    get_dong_boundaries,
    point_in_feature,
    polygon_area_m2,
    polygon_bbox,
)
from app.data_provider.local.foot_traffic_loader import get_foot_traffic_for_dong
from app.data_provider.local.population_loader import get_population_by_gu
from app.data_provider.local.restaurant_loader import get_restaurants_with_admin_dong
from app.data_provider.local.sanggabu_loader import get_sanggabu_busan
from app.schemas import (
    AlternativeRegion,
    GridCellBounds,
    GridCellDetailResponse,
    GridCellSummary,
    GridResponse,
    RegionInfo,
    ScoreBreakdown,
    ScoreResult,
    ScoreWeights,
)
from app.scoring import _CATEGORY_TO_REVENUE_BUCKET, _WEIGHTS  # scoring.py와 항상 같은 값 유지

_CELL_SIZES_M = (100, 250, 500, 1000)
_TARGET_CELL_COUNT = 50
_MIN_CLOSURE_SAMPLE = 5  # local_provider.py의 동일 상수와 같은 기준(조사 결과)
_RECENT_CLOSURE_WINDOW_DAYS = 365


def _to_sanggabu_code(region_id: str) -> int:
    return int(region_id) // 100


def _choose_cell_size_m(area_m2: float) -> int:
    """면적을 목표 셀 개수(~50개)에 가장 가깝게 맞추는 값을 100/250/500/1000m 중에서 고른다."""
    ideal = math.sqrt(area_m2 / _TARGET_CELL_COUNT)
    return min(_CELL_SIZES_M, key=lambda m: abs(m - ideal))


def _normalize_local(value: float, values: list[float]) -> int:
    """이 행정동 격자들 사이의 min~max로 정규화 (scoring.py의 _normalize와 같은 형태,
    상/하한만 도시 전체 상수 대신 이 동 격자들 자체의 분포를 씀)."""
    low, high = min(values), max(values)
    if high <= low:
        return 50
    ratio = (value - low) / (high - low)
    return round(max(0.0, min(1.0, ratio)) * 100)


@dataclass
class _Cell:
    row: int
    col: int
    center_lon: float
    center_lat: float
    bounds: tuple[float, float, float, float]  # north, south, east, west
    poi_weight: float = 0.0
    competitor_count: int = 0
    closure_active: int = 0
    closure_closed_recent: int = 0
    closure_rate: float = 0.0
    closure_available: bool = False
    breakdown: ScoreBreakdown | None = None
    total_score: int = 0
    data_limitations: list[str] = field(default_factory=list)

    @property
    def cell_id(self) -> str:
        return f"{self.row}_{self.col}"

    @property
    def label(self) -> str:
        col_letter = chr(ord("A") + self.col) if self.col < 26 else f"C{self.col}"
        return f"{col_letter}-{self.row + 1}"


def _label_for_dong(행정동명: str, cell: _Cell) -> str:
    return f"{행정동명} (격자 {cell.label})"


def _generate_cells(feature: dict, cell_size_m: int) -> list[_Cell]:
    min_lon, max_lon, min_lat, max_lat = polygon_bbox(feature)
    lat_mid = (min_lat + max_lat) / 2
    m_per_deg_lat = 111_320
    m_per_deg_lon = 111_320 * math.cos(math.radians(lat_mid))
    step_lon = cell_size_m / m_per_deg_lon
    step_lat = cell_size_m / m_per_deg_lat

    n_cols = max(1, math.ceil((max_lon - min_lon) / step_lon))
    n_rows = max(1, math.ceil((max_lat - min_lat) / step_lat))

    cells = []
    for row in range(n_rows):
        for col in range(n_cols):
            west = min_lon + col * step_lon
            east = west + step_lon
            south = min_lat + row * step_lat
            north = south + step_lat
            center_lon, center_lat = (west + east) / 2, (south + north) / 2
            if point_in_feature(center_lon, center_lat, feature):
                cells.append(_Cell(row, col, center_lon, center_lat, (north, south, east, west)))
    return cells


def _competitor_mask(df: pd.DataFrame, category: str) -> pd.Series:
    """get_competitors()와 같은 분류 규칙(카테고리 4개 dict) — local_provider.py를
    호출하지 않고 여기서 다시 쓰는 이유: 그쪽은 "행정동 전체 1개 조회"용이라
    격자별로 반복 호출하면 비효율적이고, 여기서는 이미 이 행정동으로 좁혀둔
    df 하나에 벡터화된 마스크만 있으면 된다(회귀 위험도 줄임 — local_provider.py
    자체는 이번 기능에서 전혀 수정하지 않았다)."""
    if category in FOOD_SUBCATEGORIES:
        jungbunlyu = FOOD_SUBCATEGORY_TO_SANGGABU_JUNGBUNLYU.get(category)
        if jungbunlyu is None:  # 기타음식점
            return (df["상권업종대분류명"] == "음식") & ~df["상권업종중분류명"].isin(
                SANGGABU_FOOD_JUNGBUNLYU_EXCLUDE_FOR_OTHER
            )
        return df["상권업종중분류명"] == jungbunlyu
    keyword = CATEGORY_TO_SANGGABU_KEYWORD.get(category, category)
    return df["표준산업분류명"].str.contains(keyword, na=False)


def _restaurant_mask(df: pd.DataFrame, category: str) -> pd.Series | None:
    """None이면 이 업종은 폐업 이력 데이터 자체가 없음(카페/편의점/미용실)."""
    if category == "기타음식점":
        return ~df["업태구분명"].isin(RESTAURANT_UPTAE_EXCLUDE_FOR_OTHER)
    uptae = CATEGORY_TO_RESTAURANT_UPTAE.get(category)
    if uptae is None:
        return None
    return df["업태구분명"] == uptae


def compute_grid(region_id: str, category: str, 시군구명: str) -> tuple[list[_Cell], int]:
    """이 행정동의 격자 셀 전체(원자료+점수 계산 완료)를 만든다. 두 엔드포인트
    (목록용 GridResponse, 셀 상세용 GridCellDetailResponse)가 이 결과를 공유한다."""
    boundaries = get_dong_boundaries()
    feature = boundaries.get(region_id)
    if feature is None:
        raise ValueError(f"행정동 경계를 찾을 수 없음: {region_id}")

    area_m2 = polygon_area_m2(feature)
    cell_size_m = _choose_cell_size_m(area_m2)
    cells = _generate_cells(feature, cell_size_m)
    if not cells:
        raise ValueError(f"격자를 생성하지 못함(면적이 너무 작음): {region_id}")

    code8 = _to_sanggabu_code(region_id)

    # ---- 경쟁업체 수 + POI 밀도(전체 업종) ----
    sanggabu = get_sanggabu_busan()
    dong_biz = sanggabu[sanggabu["행정동코드"] == code8]
    competitor_mask = _competitor_mask(dong_biz, category)
    competitor_biz = dong_biz[competitor_mask]

    for cell in cells:
        north, south, east, west = cell.bounds
        in_cell = (
            (dong_biz["경도"] >= west)
            & (dong_biz["경도"] < east)
            & (dong_biz["위도"] >= south)
            & (dong_biz["위도"] < north)
        )
        cell.poi_weight = float(in_cell.sum())
        cell.competitor_count = int((competitor_mask & in_cell).sum())

    total_poi = sum(c.poi_weight for c in cells) or 1.0  # 상가업소가 아예 없으면 균등 배분

    # ---- 폐업률 (있는 업종만) ----
    if category == "기타음식점" or CATEGORY_TO_RESTAURANT_UPTAE.get(category) is not None:
        restaurants = get_restaurants_with_admin_dong()
        dong_rest = restaurants[restaurants["행정동코드"] == code8].copy()
        mask = _restaurant_mask(dong_rest, category)
        dong_rest = dong_rest[mask] if mask is not None else dong_rest.iloc[0:0]

        cutoff = pd.Timestamp.now() - pd.Timedelta(days=_RECENT_CLOSURE_WINDOW_DAYS)
        폐업일자 = pd.to_datetime(dong_rest["폐업일자"], errors="coerce")
        active_mask = dong_rest["영업상태명"] == "영업/정상"
        closed_recent_mask = (dong_rest["영업상태명"] == "폐업") & (폐업일자 >= cutoff)

        for cell in cells:
            north, south, east, west = cell.bounds
            in_cell = (
                (dong_rest["경도"] >= west)
                & (dong_rest["경도"] < east)
                & (dong_rest["위도"] >= south)
                & (dong_rest["위도"] < north)
            )
            cell.closure_active = int((active_mask & in_cell).sum())
            cell.closure_closed_recent = int((closed_recent_mask & in_cell).sum())
            sample = cell.closure_active + cell.closure_closed_recent
            if sample >= _MIN_CLOSURE_SAMPLE:
                cell.closure_available = True
                cell.closure_rate = round(cell.closure_closed_recent / sample * 100, 1)

    # ---- 배후수요/수익성 원재료: 행정동 단위 값을 POI 밀도 비율로 배분 ----
    foot_traffic = get_foot_traffic_for_dong(region_id)
    dong_total_visits = sum(h.평균방문인구수 for h in foot_traffic)

    population = get_population_by_gu().get(시군구명)
    dong_population = population.총인구수 if population else 0

    consumption = get_consumption_by_category_for_dong(region_id)
    bucket = _CATEGORY_TO_REVENUE_BUCKET.get(category)
    dong_revenue = next((c.평균이용금액 for c in consumption if c.업종대분류 == bucket), 0) if bucket else 0

    visit_inputs, population_inputs, revenue_inputs = [], [], []
    for cell in cells:
        weight = cell.poi_weight / total_poi
        visit_inputs.append(dong_total_visits * weight)
        population_inputs.append(dong_population * weight)
        revenue_inputs.append(dong_revenue * weight)

    # ---- 정규화(이 행정동 격자들끼리 상대비교) + 가중합 ----
    competitor_counts = [c.competitor_count for c in cells]
    closure_rates = [c.closure_rate for c in cells if c.closure_available]

    for i, cell in enumerate(cells):
        visit_score = _normalize_local(visit_inputs[i], visit_inputs)
        population_score = _normalize_local(population_inputs[i], population_inputs)
        demand = round(visit_score * 0.5 + population_score * 0.5)

        density_congestion = _normalize_local(cell.competitor_count, competitor_counts)
        notes = []
        if cell.closure_available and len(closure_rates) > 1:
            closure_congestion = _normalize_local(cell.closure_rate, closure_rates)
            congestion = round(density_congestion * 0.5 + closure_congestion * 0.5)
        else:
            congestion = density_congestion
            sample = cell.closure_active + cell.closure_closed_recent
            if category in FOOD_SUBCATEGORIES and sample > 0:
                notes.append(f"이 격자는 '{category}' 업태 표본이 {sample}건뿐이라 폐업률을 신뢰할 수 없어 제외함")
            elif category in FOOD_SUBCATEGORIES:
                notes.append(f"이 격자에는 '{category}' 업태 표본이 없어 폐업률을 계산할 수 없음")
            else:
                notes.append(f"'{category}' 업종은 폐업 이력 데이터가 없어 경쟁강도를 밀집도만으로 산정")
        competition = 100 - congestion

        profitability = _normalize_local(revenue_inputs[i], revenue_inputs) if bucket else 50
        if bucket is None:
            notes.append(f"'{category}' 업종은 매출 카테고리 매핑이 없어 수익성 점수를 50(중간값)으로 처리")

        total = round(demand * _WEIGHTS["배후수요"] + competition * _WEIGHTS["경쟁강도"] + profitability * _WEIGHTS["수익성"])

        cell.breakdown = ScoreBreakdown(배후수요=demand, 경쟁강도=competition, 접근성=None, 수익성=profitability)
        cell.total_score = total
        cell.data_limitations = notes

    return cells, cell_size_m


def to_grid_response(region_id: str, 행정동명: str, category: str, cells: list, cell_size_m: int) -> GridResponse:
    return GridResponse(
        region_id=region_id,
        행정동명=행정동명,
        category=category,
        cell_size_m=cell_size_m,
        cells=[
            GridCellSummary(
                cell_id=cell.cell_id,
                center_위도=cell.center_lat,
                center_경도=cell.center_lon,
                bounds=GridCellBounds(
                    north=cell.bounds[0], south=cell.bounds[1], east=cell.bounds[2], west=cell.bounds[3]
                ),
                total_score=cell.total_score,
                breakdown=cell.breakdown,
            )
            for cell in cells
        ],
    )


def to_cell_detail(region_id: str, 행정동명: str, cells: list, cell_id: str) -> GridCellDetailResponse:
    target = next((c for c in cells if c.cell_id == cell_id), None)
    if target is None:
        raise ValueError(f"격자 셀을 찾을 수 없음: {cell_id}")

    region_by_id: dict[str, RegionInfo] = {}
    all_scores: dict[str, ScoreResult] = {}
    for cell in cells:
        cell_region_id = f"{region_id}_{cell.cell_id}"
        region_by_id[cell_region_id] = RegionInfo(
            region_id=cell_region_id,
            행정동코드=region_id,
            행정동명=_label_for_dong(행정동명, cell),
            시도명="부산광역시",
            시군구명="",
            위도=cell.center_lat,
            경도=cell.center_lon,
        )
        all_scores[cell_region_id] = ScoreResult(
            total_score=cell.total_score,
            breakdown=cell.breakdown,
            weights_used=ScoreWeights(
                배후수요=_WEIGHTS["배후수요"], 경쟁강도=_WEIGHTS["경쟁강도"], 접근성=0.0, 수익성=_WEIGHTS["수익성"]
            ),
            data_limitations=cell.data_limitations,
            is_placeholder=False,
        )

    target_region_id = f"{region_id}_{target.cell_id}"
    alternatives: list[AlternativeRegion] = []
    if target.total_score <= LOW_SCORE_THRESHOLD:
        alternatives = find_alternatives(
            region_by_id[target_region_id], target.total_score, all_scores, region_by_id
        )

    return GridCellDetailResponse(
        cell_id=cell_id,
        label=_label_for_dong(행정동명, target),
        total_score=target.total_score,
        breakdown=target.breakdown,
        competitor_count=target.competitor_count,
        closure_available=target.closure_available,
        closure_rate=target.closure_rate,
        closure_sample=target.closure_active + target.closure_closed_recent,
        data_limitations=target.data_limitations,
        alternatives=alternatives,
    )
