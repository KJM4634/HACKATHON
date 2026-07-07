"""
스코어링 엔진 (PRD 3.3 Track B 가중합).

PRD 원안 가중치: 배후수요 0.35 + 경쟁강도 0.3(역가중) + 접근성 0.2 + 수익성 0.15

실제 확보 데이터로는 접근성(대중교통 정류장·집객시설 근접도)을 계산할 수 없어
제외했다 — data_inventory.md의 어떤 데이터셋에도 지하철역/버스정류장/학교/오피스
같은 POI가 없다. 남은 세 지표의 가중치는 원래 비율(0.35:0.30:0.15)을 유지한 채
합이 1.0이 되도록 재분배했다:

    배후수요 0.4375 / 경쟁강도 0.375 / 수익성 0.1875 (접근성 0)

경쟁강도 내부에서도 데이터 공백이 하나 더 있다: 일반음식점표준데이터(폐업률의
유일한 소스)는 "일반음식점"(한식/분식/호프 등) 인허가만 다루고 카페·편의점·
미용실은 다른 인허가 카테고리라 폐업 이력이 없다. 이 경우 경쟁강도는 폐업률
없이 동일업종 밀집도만으로 산정한다 (MarketData.closure_stats.data_available
플래그로 판단).

정규화는 부산 206개 행정동 전체의 실측 분포(P5~P95, 2026-07-08 스냅샷 기준)를
min-max 상/하한으로 써서 0~100으로 변환한다. 산출에 쓴 원시 분포는
scripts/analyze_scoring_bounds.py 로 재현할 수 있다.
"""

from app.schemas import MarketData, ScoreBreakdown, ScoreResult, ScoreWeights

# ---- PRD 원안 가중치 및 접근성 제외 후 재분배 ----
_ORIGINAL_WEIGHTS = {"배후수요": 0.35, "경쟁강도": 0.30, "접근성": 0.20, "수익성": 0.15}
_AVAILABLE_KEYS = ["배후수요", "경쟁강도", "수익성"]
_redistribution_base = sum(_ORIGINAL_WEIGHTS[k] for k in _AVAILABLE_KEYS)
_WEIGHTS = {k: _ORIGINAL_WEIGHTS[k] / _redistribution_base for k in _AVAILABLE_KEYS}
_WEIGHTS["접근성"] = 0.0

_ACCESSIBILITY_NOTE = (
    "접근성(대중교통 정류장·집객시설 근접도) 데이터가 없어 점수 산출에서 제외했고, "
    "나머지 세 지표 가중치를 원래 비율(0.35:0.30:0.15)대로 재분배함 "
    f"(배후수요 {_WEIGHTS['배후수요']:.4f} / 경쟁강도 {_WEIGHTS['경쟁강도']:.4f} / 수익성 {_WEIGHTS['수익성']:.4f})"
)

# ---- 정규화 상/하한: 부산 206개 행정동 실측 분포 P5~P95 (2026-07-08 스냅샷) ----
# 재현: scripts/analyze_scoring_bounds.py
_VISIT_POP_RANGE = (17_000, 231_000)  # 일 총 방문인구(24h 합)
_GU_POPULATION_RANGE = (36_500, 373_000)  # 구 단위 총인구수 (16개 구 min~max)
_COMPETITOR_COUNT_RANGE = {  # 업종별 행정동당 업체수
    "카페": (4, 80),
    "음식점": (15, 291),
    "편의점": (2, 28),
    "미용실": (8, 127),
}
_DEFAULT_COMPETITOR_COUNT_RANGE = (0, 100)
_CLOSURE_RATE_RANGE = (0, 17)  # %, 한식(일반음식점) 최근1년 폐업률
_REVENUE_RANGE = {  # 평균이용금액(일평균), 업종대분류 버킷
    "음식/주점": (21_000_000, 221_500_000),
    "유통": (37_000_000, 510_000_000),
    "미용": (1_700_000, 19_600_000),
}

# 사용자 선택 업종 -> 소비매출 파일의 업종대분류 버킷 (수익성 근사에 사용)
# 소비매출 데이터가 카페/음식점을 분리하지 않아 둘 다 "음식/주점"에 매핑됨
_CATEGORY_TO_REVENUE_BUCKET = {
    "카페": "음식/주점",
    "음식점": "음식/주점",
    "편의점": "유통",
    "미용실": "미용",
}


def _normalize(value: float, low: float, high: float) -> int:
    if high <= low:
        return 50
    ratio = (value - low) / (high - low)
    return round(max(0.0, min(1.0, ratio)) * 100)


def _score_demand(market_data: MarketData, notes: list[str]) -> int:
    """배후수요 = 유동인구(방문인구 총합) + 배후인구(구 단위 인구), 50:50."""
    total_visits = sum(h.평균방문인구수 for h in market_data.foot_traffic)
    visit_score = _normalize(total_visits, *_VISIT_POP_RANGE)
    population_score = _normalize(market_data.population.총인구수, *_GU_POPULATION_RANGE)

    if market_data.population.is_gu_level_estimate:
        notes.append(
            f"배후인구는 행정동 실측치가 아니라 소속 구({market_data.region.시군구명}) 전체 "
            "인구를 그대로 적용한 추정치 (인구세대현황이 시군구 단위까지만 존재)"
        )

    return round(visit_score * 0.5 + population_score * 0.5)


def _score_competition(market_data: MarketData, category: str, notes: list[str]) -> int:
    """경쟁강도 = 밀집도 + 폐업률(있으면), 역가중 — 혼잡할수록 점수가 낮음."""
    count_range = _COMPETITOR_COUNT_RANGE.get(category, _DEFAULT_COMPETITOR_COUNT_RANGE)
    density_congestion = _normalize(market_data.competitors.total_count, *count_range)

    closure = market_data.closure_stats
    if closure.data_available:
        closure_congestion = _normalize(closure.폐업률, *_CLOSURE_RATE_RANGE)
        congestion = round(density_congestion * 0.5 + closure_congestion * 0.5)
    else:
        congestion = density_congestion
        notes.append(
            f"'{category}' 업종은 일반음식점표준데이터가 다루지 않는 인허가 카테고리라 "
            "폐업률을 계산할 수 없음 — 경쟁강도는 동일업종 밀집도만으로 산정"
        )

    return 100 - congestion


def _score_profitability(market_data: MarketData, category: str, notes: list[str]) -> int:
    """수익성 = 카테고리에 대응하는 소비매출 버킷의 매출액 정규화."""
    bucket = _CATEGORY_TO_REVENUE_BUCKET.get(category)
    if bucket is None:
        notes.append(f"'{category}' 업종은 매출 카테고리 매핑이 없어 수익성 점수를 50(중간값)으로 처리")
        return 50

    revenue = next(
        (c.평균이용금액 for c in market_data.consumption_by_category if c.업종대분류 == bucket), None
    )
    if revenue is None:
        notes.append(f"'{bucket}' 매출 데이터가 이 지역에 없어 수익성 점수를 50(중간값)으로 처리")
        return 50

    if bucket == "음식/주점":
        notes.append(
            "수익성은 '음식/주점' 매출 버킷(카페+음식점+주점 통합)을 근사값으로 사용 "
            "— 카페/음식점을 분리한 매출 데이터가 없음"
        )
    elif bucket == "유통" and category == "편의점":
        notes.append(
            "수익성은 '유통' 매출 버킷(편의점 포함 소매 전체)을 근사값으로 사용 "
            "— 편의점만 분리한 매출 데이터가 없음"
        )

    revenue_range = _REVENUE_RANGE.get(bucket, (0, max(revenue, 1) * 2))
    return _normalize(revenue, *revenue_range)


def compute_score(market_data: MarketData, category: str) -> ScoreResult:
    notes: list[str] = []

    demand = _score_demand(market_data, notes)
    competition = _score_competition(market_data, category, notes)
    profitability = _score_profitability(market_data, category, notes)
    notes.append(_ACCESSIBILITY_NOTE)

    total = round(
        demand * _WEIGHTS["배후수요"]
        + competition * _WEIGHTS["경쟁강도"]
        + profitability * _WEIGHTS["수익성"]
    )

    return ScoreResult(
        total_score=total,
        breakdown=ScoreBreakdown(배후수요=demand, 경쟁강도=competition, 접근성=None, 수익성=profitability),
        weights_used=ScoreWeights(
            배후수요=_WEIGHTS["배후수요"],
            경쟁강도=_WEIGHTS["경쟁강도"],
            접근성=_WEIGHTS["접근성"],
            수익성=_WEIGHTS["수익성"],
        ),
        data_limitations=notes,
        is_placeholder=False,
    )
