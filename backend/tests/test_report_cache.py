import pytest

from app.api import analyze as analyze_module
from app.schemas import ReportRequest


@pytest.fixture(autouse=True)
def _clear_cache():
    analyze_module._report_cache.clear()
    yield
    analyze_module._report_cache.clear()


def _stub_provider(monkeypatch):
    class _StubProvider:
        def list_regions(self):
            from app.schemas import RegionInfo

            return [
                RegionInfo(
                    region_id=rid,
                    행정동코드=rid,
                    행정동명="테스트동",
                    시도명="부산광역시",
                    시군구명="테스트구",
                    위도=35.1,
                    경도=129.0,
                )
                for rid in ("1000000000", "2000000000")
            ]

        def get_market_data(self, region_id, category):
            from app.schemas import (
                ClosureStats,
                CompetitorSummary,
                ConsumptionByCategory,
                FootTrafficByHour,
                MarketData,
                PopulationStats,
                RegionInfo,
            )

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


def test_second_call_with_same_combo_skips_gemini(monkeypatch):
    _stub_provider(monkeypatch)
    call_count = 0

    def _fake_generate_report(category, candidates):
        nonlocal call_count
        call_count += 1
        return "가짜 리포트", False

    monkeypatch.setattr(analyze_module, "generate_report", _fake_generate_report)

    req = ReportRequest(region_ids=["1000000000"], category="카페")
    first = analyze_module.report(req)
    second = analyze_module.report(req)

    assert call_count == 1  # 두 번째 호출은 Gemini(generate_report)를 다시 부르지 않음
    assert first == second


def test_different_region_order_is_treated_as_same_combo(monkeypatch):
    _stub_provider(monkeypatch)
    call_count = 0

    def _fake_generate_report(category, candidates):
        nonlocal call_count
        call_count += 1
        return "가짜 리포트", False

    monkeypatch.setattr(analyze_module, "generate_report", _fake_generate_report)

    analyze_module.report(ReportRequest(region_ids=["1000000000", "2000000000"], category="카페"))
    analyze_module.report(ReportRequest(region_ids=["2000000000", "1000000000"], category="카페"))

    assert call_count == 1


def test_fallback_result_is_not_cached(monkeypatch):
    _stub_provider(monkeypatch)
    call_count = 0

    def _fake_generate_report(category, candidates):
        nonlocal call_count
        call_count += 1
        return "폴백 리포트", True

    monkeypatch.setattr(analyze_module, "generate_report", _fake_generate_report)

    req = ReportRequest(region_ids=["1000000000"], category="카페")
    analyze_module.report(req)
    analyze_module.report(req)

    assert call_count == 2  # 폴백은 캐시하지 않으므로 매번 다시 시도


def test_different_category_is_a_different_cache_entry(monkeypatch):
    _stub_provider(monkeypatch)
    call_count = 0

    def _fake_generate_report(category, candidates):
        nonlocal call_count
        call_count += 1
        return "가짜 리포트", False

    monkeypatch.setattr(analyze_module, "generate_report", _fake_generate_report)

    analyze_module.report(ReportRequest(region_ids=["1000000000"], category="카페"))
    analyze_module.report(ReportRequest(region_ids=["1000000000"], category="한식"))

    assert call_count == 2


def test_include_alternatives_flag_is_part_of_cache_key(monkeypatch):
    """같은 지역/업종이라도 include_alternatives가 다르면(대안 비교 섹션 유무로
    리포트 내용 자체가 달라지므로) 별개의 캐시 항목이어야 한다."""
    _stub_provider(monkeypatch)
    call_count = 0

    def _fake_generate_report(category, candidates):
        nonlocal call_count
        call_count += 1
        return "가짜 리포트", False

    monkeypatch.setattr(analyze_module, "generate_report", _fake_generate_report)

    analyze_module.report(ReportRequest(region_ids=["1000000000"], category="카페", include_alternatives=True))
    analyze_module.report(ReportRequest(region_ids=["1000000000"], category="카페", include_alternatives=False))

    assert call_count == 2
