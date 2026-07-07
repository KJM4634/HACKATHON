from pathlib import Path

import pandas as pd
import pytest
from pyproj import Geod

from app.data_provider.local.dong_mapper import LegalToAdminDongMapper, parse_sigungu_and_legal_dong

_GEOD = Geod(ellps="WGS84")

_SANGGABU_BUSAN_PATH = (
    Path(__file__).resolve().parents[2]
    / "소상공인시장진흥공단_상가(상권)정보"
    / "소상공인시장진흥공단_상가(상권)정보_부산_202603.csv"
)

pytestmark = pytest.mark.skipif(
    not _SANGGABU_BUSAN_PATH.exists(),
    reason="원본 데이터 CSV가 없는 환경(예: 데이터 없이 clone한 경우)에서는 스킵",
)


@pytest.fixture(scope="module")
def sanggabu_busan() -> pd.DataFrame:
    return pd.read_csv(_SANGGABU_BUSAN_PATH, encoding="utf-8", low_memory=False)


@pytest.fixture(scope="module")
def mapper(sanggabu_busan) -> LegalToAdminDongMapper:
    return LegalToAdminDongMapper(sanggabu_busan)


def test_unambiguous_legal_dong_needs_no_coordinates(mapper):
    """남포동1~6가는 모두 남포동 행정동 하나로만 매핑됨 (분할 없음)."""
    assert not mapper.is_ambiguous("중구", "남포동1가")
    admin = mapper.assign("중구", "남포동1가", lon=None, lat=None)
    assert admin is not None
    assert admin.행정동명 == "남포동"


def test_ambiguous_legal_dong_detected_for_demo_targets(mapper):
    """서면(부전동)/해운대(우동)/광안리(광안동)는 모두 행정동이 여러 개로 쪼개진 케이스."""
    assert mapper.is_ambiguous("부산진구", "부전동")
    assert mapper.is_ambiguous("해운대구", "우동")
    assert mapper.is_ambiguous("수영구", "광안동")


def test_parse_sigungu_and_legal_dong_handles_both_address_formats(mapper):
    assert parse_sigungu_and_legal_dong("부산광역시 부산진구 부전동 200-1", mapper) == ("부산진구", "부전동")
    assert parse_sigungu_and_legal_dong(
        "부산광역시 중구 대청로 140-8, 1층 (중앙동2가)", mapper
    ) == ("중구", "중앙동2가")
    assert parse_sigungu_and_legal_dong("서울특별시 강남구 역삼동 1", mapper) is None
    assert parse_sigungu_and_legal_dong(None, mapper) is None


def _leave_one_out_accuracy(sanggabu: pd.DataFrame, sigungu: str, legal_dong: str) -> float:
    """상가(상권)정보의 실측 행정동 라벨을 지우고 최근접 매칭으로 다시 맞혀본 정확도."""
    pts = sanggabu.loc[
        (sanggabu["시군구명"] == sigungu) & (sanggabu["법정동명"] == legal_dong),
        ["경도", "위도", "행정동코드"],
    ].dropna(subset=["경도", "위도"]).reset_index(drop=True)

    correct = 0
    for i in range(len(pts)):
        target = pts.iloc[i]
        others = pts.drop(index=i)
        _, _, dist = _GEOD.inv(
            [target["경도"]] * len(others), [target["위도"]] * len(others),
            others["경도"].to_numpy(), others["위도"].to_numpy(),
        )
        if others.iloc[dist.argmin()]["행정동코드"] == target["행정동코드"]:
            correct += 1
    return correct / len(pts)


@pytest.mark.parametrize(
    "sigungu,legal_dong",
    [("부산진구", "부전동"), ("해운대구", "우동"), ("수영구", "광안동")],
)
def test_nearest_match_accuracy_on_demo_target_dongs(sanggabu_busan, sigungu, legal_dong):
    """서면/해운대/광안리처럼 분할된 지역에서 최근접 매칭 정확도가 95% 이상이어야 한다.

    2026-07-08 실측: 부전동 100.0%, 우동 100.0%, 광안동 99.7%."""
    accuracy = _leave_one_out_accuracy(sanggabu_busan, sigungu, legal_dong)
    assert accuracy >= 0.95, f"{sigungu} {legal_dong} 정확도 {accuracy:.1%} — 95% 미달"
