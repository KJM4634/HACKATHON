import pytest

from app.api import analyze as analyze_module
from app.home_distance import estimate_home_distance
from app.schemas import ReportRequest


def test_same_point_is_zero_distance():
    fit = estimate_home_distance(35.1, 129.0, 35.1, 129.0)
    assert fit.distance_km == 0.0


def test_known_distance_roughly_matches_haversine():
    # 서면(부전2동) 근방 두 좌표, haversine 계산과 별도로 대략 1km 안팎이어야 함
    fit = estimate_home_distance(35.1554, 129.0586, 35.1650, 129.0650)
    assert 1.0 < fit.distance_km < 1.5


@pytest.fixture(autouse=True)
def _clear_cache():
    analyze_module._report_cache.clear()
    yield
    analyze_module._report_cache.clear()


def _stub_provider(monkeypatch):
    from app.schemas import (
        ClosureStats,
        CompetitorSummary,
        ConsumptionByCategory,
        FootTrafficByHour,
        MarketData,
        PopulationStats,
        RegionInfo,
    )

    class _StubProvider:
        def list_regions(self):
            return [
                RegionInfo(
                    region_id="1000000000",
                    행정동코드="1000000000",
                    행정동명="테스트동",
                    시도명="부산광역시",
                    시군구명="테스트구",
                    위도=35.1,
                    경도=129.0,
                )
            ]

        def get_market_data(self, region_id, category):
            region = RegionInfo(
                region_id=region_id,
                행정동코드=region_id,
                행정동명="테스트동",
                시도명="부산광역시",
                시군구명="테스트구",
                위도=35.1,
                경도=129.0,
            )
            return MarketData(
                region=region,
                population=PopulationStats(
                    기준연도=2025, 총인구수=1000, 세대수=1, 세대당_인구=1.0, 남자_인구수=1, 여자_인구수=1
                ),
                foot_traffic=[FootTrafficByHour(시간대="00시", 평균주거인구수=0, 평균직장인구수=0, 평균방문인구수=100)],
                consumption_by_hour=[],
                consumption_by_category=[ConsumptionByCategory(업종대분류="음식/주점", 평균이용금액=1, 평균이용건수=1)],
                competitors=CompetitorSummary(target_category=category, total_count=1, sample=[]),
                closure_stats=ClosureStats(
                    업태구분명=category,
                    영업중_점포수=1,
                    최근1년_신규개업_수=1,
                    최근1년_폐업_수=1,
                    폐업률=1.0,
                    data_available=False,
                ),
            )

    monkeypatch.setattr(analyze_module, "get_data_provider", lambda: _StubProvider())


def test_cache_hit_still_reflects_this_requests_home_location(monkeypatch):
    """캐시된 리포트를 재사용하더라도(Gemini 재호출 없이), home_distance는 매
    요청의 집 위치를 반영해야 한다 — 이전 요청의 집 위치가 새어 들어가면 안 됨."""
    _stub_provider(monkeypatch)
    call_count = 0

    def _fake_generate_report(category, candidates):
        nonlocal call_count
        call_count += 1
        return "가짜 리포트", False

    monkeypatch.setattr(analyze_module, "generate_report", _fake_generate_report)

    req_home_a = ReportRequest(region_ids=["1000000000"], category="카페", home_lat=35.10, home_lng=129.00)
    req_home_b = ReportRequest(region_ids=["1000000000"], category="카페", home_lat=35.20, home_lng=129.10)
    req_no_home = ReportRequest(region_ids=["1000000000"], category="카페")

    first = analyze_module.report(req_home_a)
    second = analyze_module.report(req_home_b)
    third = analyze_module.report(req_no_home)

    assert call_count == 1  # 셋 다 캐시 히트(첫 호출만 Gemini 실제 호출)

    assert first.candidates[0].home_distance.distance_km == 0.0
    assert second.candidates[0].home_distance.distance_km > 0.0
    assert third.candidates[0].home_distance is None  # 위치 없이 물으면 항상 None

    # 캐시에 저장된 원본 객체 자체는 home_distance로 오염되지 않아야 한다
    cache_key = (("1000000000",), "카페", True, None)
    cached_raw = analyze_module._report_cache[cache_key]
    assert cached_raw.candidates[0].home_distance is None
