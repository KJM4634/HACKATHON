from app.schemas import (
    ClosureStats,
    CompetitorSummary,
    ConsumptionByCategory,
    FootTrafficByHour,
    MarketData,
    PopulationStats,
    RegionInfo,
)
from app.scoring import compute_score

_REGION = RegionInfo(
    region_id="0000000000",
    행정동코드="0000000000",
    행정동명="테스트구 테스트동",
    시도명="부산광역시",
    시군구명="테스트구",
    위도=35.1,
    경도=129.0,
)


def _market_data(
    total_visits: int,
    population: int,
    competitor_count: int,
    closure_available: bool,
    closure_rate: float,
    revenue_bucket: str,
    revenue: int,
) -> MarketData:
    return MarketData(
        region=_REGION,
        population=PopulationStats(
            기준연도=2025, 총인구수=population, 세대수=1, 세대당_인구=1.0, 남자_인구수=1, 여자_인구수=1
        ),
        foot_traffic=[FootTrafficByHour(시간대="00시", 평균주거인구수=0, 평균직장인구수=0, 평균방문인구수=total_visits)],
        consumption_by_hour=[],
        consumption_by_category=[ConsumptionByCategory(업종대분류=revenue_bucket, 평균이용금액=revenue, 평균이용건수=1)],
        competitors=CompetitorSummary(target_category="테스트", total_count=competitor_count, sample=[]),
        closure_stats=ClosureStats(
            업태구분명="테스트",
            영업중_점포수=competitor_count,
            최근1년_신규개업_수=0,
            최근1년_폐업_수=0,
            폐업률=closure_rate,
            data_available=closure_available,
        ),
    )


def test_weights_are_redistributed_after_dropping_accessibility():
    """접근성 데이터가 없으니 0.35:0.30:0.15 비율을 유지한 채 합 1.0으로 재분배돼야 한다."""
    md = _market_data(50_000, 200_000, 50, True, 5.0, "음식/주점", 100_000_000)
    result = compute_score(md, "한식")

    weights = result.weights_used
    assert weights.접근성 == 0.0
    assert abs(weights.배후수요 + weights.경쟁강도 + weights.수익성 - 1.0) < 1e-9
    assert abs(weights.배후수요 - 0.35 / 0.80) < 1e-6
    assert abs(weights.경쟁강도 - 0.30 / 0.80) < 1e-6
    assert abs(weights.수익성 - 0.15 / 0.80) < 1e-6
    assert result.breakdown.접근성 is None
    assert any("접근성" in note for note in result.data_limitations)


def test_total_score_matches_weighted_breakdown():
    md = _market_data(50_000, 200_000, 50, True, 5.0, "음식/주점", 100_000_000)
    result = compute_score(md, "한식")
    b, w = result.breakdown, result.weights_used

    expected = round(b.배후수요 * w.배후수요 + b.경쟁강도 * w.경쟁강도 + b.수익성 * w.수익성)
    assert result.total_score == expected


def test_missing_closure_data_falls_back_to_density_only():
    """카페/편의점/미용실처럼 폐업 데이터가 없으면 밀집도만으로 경쟁강도를 계산해야 한다."""
    with_closure = _market_data(50_000, 200_000, 50, True, 20.0, "음식/주점", 100_000_000)
    without_closure = _market_data(50_000, 200_000, 50, False, 0.0, "음식/주점", 100_000_000)

    result_with = compute_score(with_closure, "한식")
    result_without = compute_score(without_closure, "카페")

    # 밀집도(50개)는 동일하지만 폐업률 반영 여부가 달라 경쟁강도 점수가 달라야 함
    assert result_with.breakdown.경쟁강도 != result_without.breakdown.경쟁강도
    assert any("폐업률을 계산할 수 없음" in note for note in result_without.data_limitations)


def test_higher_visits_and_population_score_higher_demand():
    low = _market_data(10_000, 40_000, 30, True, 5.0, "음식/주점", 50_000_000)
    high = _market_data(200_000, 350_000, 30, True, 5.0, "음식/주점", 50_000_000)

    assert compute_score(high, "한식").breakdown.배후수요 > compute_score(low, "한식").breakdown.배후수요


def test_more_competitors_lowers_competition_score():
    sparse = _market_data(50_000, 200_000, 5, True, 5.0, "음식/주점", 50_000_000)
    crowded = _market_data(50_000, 200_000, 250, True, 5.0, "음식/주점", 50_000_000)

    assert compute_score(crowded, "한식").breakdown.경쟁강도 < compute_score(sparse, "한식").breakdown.경쟁강도


def test_missing_revenue_bucket_defaults_to_midpoint():
    md = _market_data(50_000, 200_000, 50, True, 5.0, "다른버킷", 100_000_000)
    result = compute_score(md, "한식")

    assert result.breakdown.수익성 == 50
    assert any("수익성 점수를 50" in note for note in result.data_limitations)


def test_scores_are_clamped_to_0_100():
    extreme_low = _market_data(0, 0, 0, True, 0.0, "음식/주점", 0)
    extreme_high = _market_data(10_000_000, 10_000_000, 10_000, True, 100.0, "음식/주점", 10_000_000_000)

    for md in (extreme_low, extreme_high):
        result = compute_score(md, "한식")
        assert 0 <= result.total_score <= 100
        assert 0 <= result.breakdown.배후수요 <= 100
        assert 0 <= result.breakdown.경쟁강도 <= 100
        assert 0 <= result.breakdown.수익성 <= 100
