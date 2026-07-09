"""
스코어링 엔진 (PRD 3.3 Track B 가중합).

가중치 조정 히스토리(자세한 근거는 ARCHITECTURE.md "가중치 조정의 통계적 한계"
섹션 참고):

1) PRD 원안: 배후수요 0.35 + 경쟁강도 0.3(역가중) + 접근성 0.2 + 수익성 0.15
   — 다만 이 숫자 자체는 PRD에 "전문가 가중치 (예: ...)"라고만 적혀 있고 별도
   근거 문서·설문·연구는 없는 예시값이었다.
2) 접근성(대중교통 정류장·집객시설 근접도)은 실제 확보 데이터로 계산할 수 없어
   제외 — data_inventory.md의 어떤 데이터셋에도 지하철역/버스정류장/학교/오피스
   같은 POI가 없다. 나머지 세 지표 비율(0.35:0.30:0.15)을 유지한 채 재분배해
   배후수요 0.4375 / 경쟁강도 0.375 / 수익성 0.1875로 시작했다.
3) Track A(RandomForest, 한식 폐업위험 예측) feature importance를 뽑아보니
   경쟁강도(특히 폐업률)가 배후수요보다 훨씬 중요하다는 반대 방향 신호가
   나왔다(정규화 시 경쟁강도 68.7% : 배후수요 31.2% — 수익성은 Track A에 해당
   변수 자체가 없어 비교 불가). PRD 원안 비율과 이 신호를 50:50 블렌드해
   경쟁강도 0.4669까지 올리는 걸 검토했다.
4) 그런데 206개 행정동 전체로 재계산해보니, 배후수요·수익성이 낮은데 경쟁강도만
   높게 나오는 지역(예: 부산진구 개금2동)이 부당하게 상위권으로 뛰는 부작용이
   확인됐다. 상관관계 분석 결과 배후수요-경쟁강도 상관계수가 -0.521로 강하지만
   완전한 1.0이 아니라서, 이런 "상관관계를 벗어나는 예외 지역"이 소수가 아니라
   구조적으로 반복된다는 걸 확인했다(가야1동·감만1동·범일2동·명지1동·민락동도
   같은 패턴). 이 부작용을 완전히 없애려면 배후수요/수익성 하한 게이팅 같은
   구조적 안전장치가 필요하지만, 이번에는 그렇게까지 가지 않고 "0.42~0.43 범위
   안에서 부작용이 최소인 지점"으로 조정하는 선에서 최종 결정했다(경쟁강도를
   0.420/0.423/0.425/0.428/0.430으로 각각 계산해보니 부작용이 단조증가해서
   범위 하한인 0.420을 채택).

    배후수요 0.3925 / 경쟁강도 0.420 / 수익성 0.1875 (접근성 0)

경쟁강도 내부에서도 데이터 공백이 있다: 카페·편의점·미용실은 일반음식점표준
데이터가 다루는 인허가 카테고리가 아니라 폐업 이력이 구조적으로 없다. 음식점
서브카테고리(한식/중식/분식/기타음식점)는 폐업 이력 자체는 있지만, 표본이
5건 미만인 지역은 노이즈에 가까워 마찬가지로 제외한다(둘 다
MarketData.closure_stats.data_available=False로 표시). 두 경우 모두 경쟁강도는
폐업률 없이 동일업종 밀집도만으로 산정한다.

정규화는 부산 206개 행정동 전체의 실측 분포(P5~P95, 2026-07-08 스냅샷 기준)를
min-max 상/하한으로 써서 0~100으로 변환한다. 산출에 쓴 원시 분포는
scripts/analyze_scoring_bounds.py 로 재현할 수 있다.
"""

from app.data_provider.local.category_mapping import FOOD_SUBCATEGORIES
from app.ml.predict import predict_track_a
from app.schemas import MarketData, ScoreBreakdown, ScoreResult, ScoreWeights

# ---- 최종 가중치 (위 히스토리 4번 참고) ----
_WEIGHTS = {"배후수요": 0.3925, "경쟁강도": 0.420, "수익성": 0.1875, "접근성": 0.0}

_ACCESSIBILITY_NOTE = (
    "접근성(대중교통 정류장·집객시설 근접도) 데이터가 없어 점수 산출에서 제외했고, "
    "나머지 세 지표 가중치를 재조정함(PRD 원안 + Track A 신호 블렌드 후 부작용 완화 목적 최종 조정 — "
    "자세한 근거는 ARCHITECTURE.md 참고) "
    f"(배후수요 {_WEIGHTS['배후수요']:.4f} / 경쟁강도 {_WEIGHTS['경쟁강도']:.4f} / 수익성 {_WEIGHTS['수익성']:.4f})"
)

# ---- 정규화 상/하한: 부산 206개 행정동 실측 분포 P5~P95 (2026-07-08 스냅샷) ----
# 재현: scripts/analyze_scoring_bounds.py
_VISIT_POP_RANGE = (17_000, 231_000)  # 일 총 방문인구(24h 합)
_GU_POPULATION_RANGE = (36_500, 373_000)  # 구 단위 총인구수 (16개 구 min~max)
_COMPETITOR_COUNT_RANGE = {  # 업종별 행정동당 업체수 (음식점 서브카테고리는 상권업종중분류명 정확매칭 기준)
    "카페": (4, 80),
    "한식": (14, 280),
    "중식": (1, 23),
    "분식": (5, 113),
    "기타음식점": (2, 204),
    "편의점": (2, 28),
    "미용실": (8, 127),
}
_DEFAULT_COMPETITOR_COUNT_RANGE = (0, 100)
_CLOSURE_RATE_RANGE = {  # %, 최근1년 폐업률 (표본 5건 미만 행정동은 제외하고 산출)
    "한식": (0, 16),
    "중식": (0, 20),
    "분식": (0, 23),
    "기타음식점": (0, 22),
}
_DEFAULT_CLOSURE_RATE_RANGE = (0, 20)
_REVENUE_RANGE = {  # 평균이용금액(일평균), 업종대분류 버킷
    "음식/주점": (21_000_000, 221_500_000),
    "유통": (37_000_000, 510_000_000),
    "미용": (1_700_000, 19_600_000),
}

# 사용자 선택 업종 -> 소비매출 파일의 업종대분류 버킷 (수익성 근사에 사용)
# 소비매출 데이터가 카페와 음식점 서브카테고리(한식/중식/분식/기타음식점)를 분리하지
# 않아 5개 모두 "음식/주점"에 매핑됨 — 이 5개는 수익성 숫자 자체를 공유한다.
_CATEGORY_TO_REVENUE_BUCKET = {
    "카페": "음식/주점",
    "한식": "음식/주점",
    "중식": "음식/주점",
    "분식": "음식/주점",
    "기타음식점": "음식/주점",
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
        rate_range = _CLOSURE_RATE_RANGE.get(category, _DEFAULT_CLOSURE_RATE_RANGE)
        closure_congestion = _normalize(closure.폐업률, *rate_range)
        congestion = round(density_congestion * 0.5 + closure_congestion * 0.5)
    else:
        congestion = density_congestion
        sample = closure.영업중_점포수 + closure.최근1년_폐업_수
        if category in FOOD_SUBCATEGORIES and sample > 0:
            notes.append(
                f"이 지역은 '{category}' 업태 표본이 {sample}건뿐이라 폐업률을 신뢰할 수 없어 제외함 "
                "— 경쟁강도는 동일업종 밀집도만으로 산정"
            )
        elif category in FOOD_SUBCATEGORIES:
            notes.append(
                f"이 지역에는 '{category}' 업태 표본이 아예 없어 폐업률을 계산할 수 없음 "
                "— 경쟁강도는 동일업종 밀집도만으로 산정"
            )
        else:
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
            "— 카페와 음식점 서브카테고리(한식/중식/분식/기타음식점)를 분리한 매출 데이터가 없어 "
            "5개 카테고리 모두 이 버킷을 그대로 공유함(같은 지역이면 수익성 숫자가 동일)"
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
        track_a=predict_track_a(market_data, category),
    )
