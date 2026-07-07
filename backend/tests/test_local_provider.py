from pathlib import Path

import pytest

from app.data_provider.local.local_provider import LocalDataProvider
from app.scoring import compute_score

_DATA_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    not (_DATA_ROOT / "소상공인시장진흥공단_상가(상권)정보").exists(),
    reason="원본 데이터 CSV가 없는 환경에서는 스킵",
)

_DEMO_REGIONS = {
    "서면": "2623052000",
    "남포동": "2611058000",
    "해운대": "2635051000",
    "광안리": "2650077000",
}


@pytest.fixture(scope="module")
def provider() -> LocalDataProvider:
    return LocalDataProvider()


def test_region_info_matches_known_dong(provider):
    info = provider.get_region_info(_DEMO_REGIONS["서면"])
    assert info.행정동명 == "부산진구 부전2동"
    assert info.시군구명 == "부산진구"

    info = provider.get_region_info(_DEMO_REGIONS["해운대"])
    assert info.행정동명 == "해운대구 우1동"


def test_unknown_region_id_raises_value_error(provider):
    with pytest.raises(ValueError):
        provider.get_region_info("9999999999")


def test_population_is_gu_level_estimate(provider):
    """중구(남포동 소속)는 부산 16개 구 중 인구가 가장 적어야 한다 — 원도심 특성 반영."""
    nampo_pop = provider.get_population(_DEMO_REGIONS["남포동"])
    haeundae_pop = provider.get_population(_DEMO_REGIONS["해운대"])

    assert nampo_pop.is_gu_level_estimate is True
    assert nampo_pop.총인구수 < haeundae_pop.총인구수


def test_closure_data_available_only_for_음식점(provider):
    for category in ["카페", "편의점", "미용실"]:
        closure = provider.get_closure_stats(_DEMO_REGIONS["서면"], category)
        assert closure.data_available is False

    closure = provider.get_closure_stats(_DEMO_REGIONS["서면"], "음식점")
    assert closure.data_available is True
    assert closure.영업중_점포수 > 0


def test_competitor_counts_match_known_values(provider):
    """2026-07-08 실측 검증값 (data_inventory.md 조사 결과와 동일해야 함)."""
    expected = {
        "서면": {"카페": 133, "음식점": 507, "편의점": 53, "미용실": 298},
        "남포동": {"카페": 40, "음식점": 220, "편의점": 11, "미용실": 76},
        "해운대": {"카페": 77, "음식점": 241, "편의점": 39, "미용실": 91},
        "광안리": {"카페": 76, "음식점": 172, "편의점": 18, "미용실": 120},
    }
    for name, region_id in _DEMO_REGIONS.items():
        for category, count in expected[name].items():
            summary = provider.get_competitors(region_id, category)
            assert summary.total_count == count, f"{name} {category}: {summary.total_count} != {count}"


@pytest.mark.parametrize("name,region_id", list(_DEMO_REGIONS.items()))
@pytest.mark.parametrize("category", ["카페", "음식점", "편의점", "미용실"])
def test_analyze_pipeline_produces_valid_score(provider, name, region_id, category):
    market_data = provider.get_market_data(region_id, category)
    result = compute_score(market_data, category)

    assert 0 <= result.total_score <= 100
    assert result.is_placeholder is False


def test_busiest_areas_score_higher_than_quiet_areas_for_음식점(provider):
    """번화가(서면/해운대)가 상대적으로 조용한 곳(남포동)보다 음식점 총점이 높아야 한다."""

    def total(name):
        md = provider.get_market_data(_DEMO_REGIONS[name], "음식점")
        return compute_score(md, "음식점").total_score

    assert total("해운대") > total("남포동")
    assert total("서면") > total("남포동")
