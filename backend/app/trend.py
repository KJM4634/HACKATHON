"""
"최근 추세" 배지 — 이 지역의 매출이 부산 전체 흐름 대비 빠르게 늘고 있는지
완만한지를 참고 정보로 보여준다. total_score 계산에는 전혀 반영되지 않는
보조 배지다(app/budget.py와 같은 패턴 — 새 지표를 추가하며 가중치를 또
재조정하지 않기 위함).

데이터 확인(구현 없이 조사만 한 단계에서): 일별 행정동 업종 소비매출
월별 일평균.csv가 2023-01~2025-12 36개월치를 갖고 있고 205/206개 동이
완전하다(1개 동만 2025-02부터 11개월 — 아래 참고).

QoQ(직전분기 대비)가 아니라 YoY(작년 동기 대비)를 쓰는 이유: 실측해보니
QoQ는 206개 동의 96% 이상이 같은 방향(양수)으로 움직여서 개별 동의 특성이
아니라 부산 전체에 걸리는 계절성/거시 효과에 가까웠다. YoY는 표준편차가
훨씬 커서(동별 편차 12.8%p vs QoQ 3.6%p) 계절성이 상쇄된, 동 고유의 흐름을
더 잘 보여준다.

절대 증감률을 그대로 보여주지 않고 "부산 전체 중앙값 대비 상대값"으로
판단하는 이유도 같다 — 절대값만 보여주면 "부산 전체가 오르는 시기라 이
동네도 오른 것"과 "이 동네만 특별히 빠르게 크는 것"을 구분할 수 없다.

이력 부족 처리: 소비매출 데이터 중 행정동코드 2644059000은 2025-02~2025-12
(11개월)만 있어 작년 동기(2024-10~12) 데이터 자체가 없다 — 2025년 초
신설/변경된 행정동으로 추정된다. 이런 동은 YoY 계산이 불가능하므로
data_available=False로 표시하고 "데이터 부족" 문구를 대신 보여준다.

데이터 최신성: 가장 최근 달이 2025-12라, "최근 3개월"은 실제로는
2025-10~2025-12를 뜻한다 — 이 서비스의 다른 지표(배후수요/수익성)도 같은
스냅샷을 쓰므로 새로 생기는 한계는 아니지만, "최근 추세"라는 표현 자체가
실시간처럼 들릴 수 있어 프론트 데이터 안내 문구에 명시해둔다(App.jsx).
"""

import statistics
from functools import lru_cache

from app.data_provider.local.category_mapping import CATEGORY_TO_REVENUE_BUCKET
from app.data_provider.local.consumption_loader import get_consumption_by_category_all_months
from app.schemas import TrendFit

_RECENT_MONTHS = [202510, 202511, 202512]  # 최신 스냅샷(2025-12) 기준 최근 3개월
_YEAR_AGO_MONTHS = [202410, 202411, 202412]  # 작년 동기 3개월

_INSUFFICIENT_HISTORY_LABEL = "이 지역은 최근 1년치 이력이 부족해(신설·변경된 행정동 등) 추세를 계산할 수 없습니다"


@lru_cache
def _yoy_by_dong(bucket: str) -> dict[str, float | None]:
    """업종대분류 버킷 하나에 대해 206개 행정동 각각의 YoY 증감률(%)을 계산.
    작년 동기 데이터가 3개월 모두 없는 동은 None(이력 부족)."""
    df = get_consumption_by_category_all_months()
    sub = df[df["업종대분류"] == bucket]

    result: dict[str, float | None] = {}
    for code, g in sub.groupby("행정동코드"):
        recent = g.loc[g["기준년월"].isin(_RECENT_MONTHS), "평균이용금액"]
        year_ago = g.loc[g["기준년월"].isin(_YEAR_AGO_MONTHS), "평균이용금액"]
        if len(recent) < 3 or len(year_ago) < 3:
            result[str(code)] = None
            continue
        recent_avg, year_ago_avg = recent.mean(), year_ago.mean()
        result[str(code)] = (recent_avg - year_ago_avg) / year_ago_avg * 100
    return result


@lru_cache
def _city_median_yoy(bucket: str) -> float | None:
    values = [v for v in _yoy_by_dong(bucket).values() if v is not None]
    return statistics.median(values) if values else None


def estimate_trend_fit(행정동코드: str, category: str) -> TrendFit:
    """이 동의 YoY 증감률과 부산 전체 중앙값의 차이(양수/음수)만 본다 — 양수면
    "평균보다 빠르게 성장", 음수(0 포함)면 "평균보다 완만"으로 표현한다."""
    bucket = CATEGORY_TO_REVENUE_BUCKET.get(category)
    if bucket is None:
        return TrendFit(data_available=False, label=_INSUFFICIENT_HISTORY_LABEL)

    dong_yoy = _yoy_by_dong(bucket).get(str(행정동코드))
    city_median = _city_median_yoy(bucket)
    if dong_yoy is None or city_median is None:
        return TrendFit(data_available=False, label=_INSUFFICIENT_HISTORY_LABEL)

    relative = dong_yoy - city_median
    if relative > 0:
        label = "최근 1년 매출이 부산 평균보다 빠르게 성장하는 추세를 보이고 있어, 상권이 활발해지는 편일 수 있습니다"
    else:
        label = "최근 1년 매출이 부산 평균보다 완만한 추세를 보이고 있어, 상권이 안정적으로 유지되는 편일 수 있습니다"

    return TrendFit(
        data_available=True,
        dong_yoy_pct=round(dong_yoy, 1),
        city_median_yoy_pct=round(city_median, 1),
        label=label,
    )
