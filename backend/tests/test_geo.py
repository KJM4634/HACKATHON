import pandas as pd
import pytest

from app.data_provider.geo import BUSAN_ULSAN_GYEONGNAM_BOUNDS, transform_tm5174_to_wgs84


def test_known_address_matches_sanggabu_data():
    """부산 중구 부평동3가 79-12 소재 일반음식점 좌표가, 같은 지번 블록
    (부평동3가 79-1~79-19)의 상가(상권)정보 실측 WGS84 좌표와 근접해야 한다.
    EPSG:5174 확정에 쓴 검증 사례 그대로 회귀 테스트로 고정."""
    x = pd.Series([384477.789433])
    y = pd.Series([180066.613604])

    lon, lat = transform_tm5174_to_wgs84(x, y)

    expected_lon, expected_lat = 129.0242, 35.1030
    assert abs(lon.iloc[0] - expected_lon) < 0.001  # 약 90m 이내
    assert abs(lat.iloc[0] - expected_lat) < 0.001


def test_nan_input_stays_nan():
    x = pd.Series([384477.789433, None])
    y = pd.Series([180066.613604, None])

    lon, lat = transform_tm5174_to_wgs84(x, y)

    assert pd.isna(lon.iloc[1])
    assert pd.isna(lat.iloc[1])
    assert not pd.isna(lon.iloc[0])


def test_result_within_busan_ulsan_gyeongnam_bounds():
    # 경남 진주 / 부산 중구 / 울산 중구 샘플
    x = pd.Series([298896.921605, 384477.789433, 410487.959773])
    y = pd.Series([188512.345105, 180066.613604, 231037.489447])

    lon, lat = transform_tm5174_to_wgs84(x, y)

    lon_min, lon_max = BUSAN_ULSAN_GYEONGNAM_BOUNDS["lon"]
    lat_min, lat_max = BUSAN_ULSAN_GYEONGNAM_BOUNDS["lat"]
    assert lon.between(lon_min, lon_max).all()
    assert lat.between(lat_min, lat_max).all()


def test_out_of_bounds_result_logs_warning(caplog):
    # 명백히 다른 지역(수도권 근방) 좌표를 흉내낸 값 -> 부울경 범위를 벗어나야 함
    x = pd.Series([198000.0])
    y = pd.Series([450000.0])

    with caplog.at_level("WARNING"):
        transform_tm5174_to_wgs84(x, y)

    assert any("부울경 범위를 벗어남" in record.message for record in caplog.records)


@pytest.mark.skipif(
    not (
        __import__("pathlib").Path(__file__)
        .resolve()
        .parents[2]
        .joinpath("부울경_일반음식점표준데이터", "식품_일반음식점_부산광역시.csv")
        .exists()
    ),
    reason="원본 데이터 CSV가 없는 환경(예: 데이터 없이 clone한 경우)에서는 스킵",
)
def test_restaurant_loader_produces_matching_coordinates():
    """실제 CSV 로더 통합 테스트: 알고 있는 실제 레코드(육사랑방)의 변환 좌표가
    상가(상권)정보 실측값과 근접해야 한다."""
    from app.data_provider.local.restaurant_loader import get_restaurants_wgs84

    df = get_restaurants_wgs84()

    row = df[df["관리번호"] == "3250000-101-2020-00059"]
    assert len(row) == 1

    lon = row["경도"].iloc[0]
    lat = row["위도"].iloc[0]
    assert abs(lon - 129.0242) < 0.001
    assert abs(lat - 35.1030) < 0.001

    # 원본 데이터 자체에 관할 지자체와 실제 소재지가 다른 레코드가 극소수 있음
    # (예: 관리번호 3720000-101-2019-00293 "찰리스피자"는 울산광역시 파일에 있지만
    #  지번주소는 경상북도 포항시; 관리번호 5350000-101-2025-00367은 경상남도 파일에
    #  있지만 지번주소는 대전광역시). 우리 변환 로직의 오류가 아니라 원본 데이터의
    # 이상치이므로 소수 허용 — 개수가 늘어나면(>5) 새로운 이상치가 생긴 것이니 확인 필요.
    lon_min, lon_max = BUSAN_ULSAN_GYEONGNAM_BOUNDS["lon"]
    lat_min, lat_max = BUSAN_ULSAN_GYEONGNAM_BOUNDS["lat"]
    valid = df["경도"].notna()
    in_bounds = df["경도"].between(lon_min, lon_max) & df["위도"].between(lat_min, lat_max)
    out_of_bounds_count = int((valid & ~in_bounds).sum())
    assert out_of_bounds_count <= 5, f"부울경 범위 밖 좌표 {out_of_bounds_count}건 — 새로운 이상치 여부 확인 필요"
