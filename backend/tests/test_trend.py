from app import trend as trend_module
from app.trend import estimate_trend_fit


def test_dong_above_city_median_is_flagged_growing_faster(monkeypatch):
    monkeypatch.setattr(trend_module, "_yoy_by_dong", lambda bucket: {"1111000000": 10.0})
    monkeypatch.setattr(trend_module, "_city_median_yoy", lambda bucket: 4.0)

    fit = estimate_trend_fit("1111000000", "카페")

    assert fit.data_available is True
    assert fit.dong_yoy_pct == 10.0
    assert fit.city_median_yoy_pct == 4.0
    assert "빠르게 성장" in fit.label


def test_dong_below_city_median_is_flagged_gentler(monkeypatch):
    monkeypatch.setattr(trend_module, "_yoy_by_dong", lambda bucket: {"1111000000": 1.0})
    monkeypatch.setattr(trend_module, "_city_median_yoy", lambda bucket: 5.5)

    fit = estimate_trend_fit("1111000000", "카페")

    assert fit.data_available is True
    assert "완만" in fit.label


def test_dong_exactly_at_city_median_is_flagged_gentler_not_growing(monkeypatch):
    """차이가 정확히 0이면(양수도 음수도 아님) '완만' 쪽으로 분류한다 — '성장'은
    부산 평균을 실제로 앞설 때만 쓰는 표현이어야 한다."""
    monkeypatch.setattr(trend_module, "_yoy_by_dong", lambda bucket: {"1111000000": 5.0})
    monkeypatch.setattr(trend_module, "_city_median_yoy", lambda bucket: 5.0)

    fit = estimate_trend_fit("1111000000", "카페")

    assert "완만" in fit.label


def test_missing_dong_data_is_unavailable(monkeypatch):
    monkeypatch.setattr(trend_module, "_yoy_by_dong", lambda bucket: {})
    monkeypatch.setattr(trend_module, "_city_median_yoy", lambda bucket: 5.0)

    fit = estimate_trend_fit("9999999999", "카페")

    assert fit.data_available is False
    assert fit.dong_yoy_pct is None
    assert "이력이 부족" in fit.label


def test_unmapped_category_is_unavailable():
    fit = estimate_trend_fit("1111000000", "존재하지않는업종")
    assert fit.data_available is False


def test_known_insufficient_history_dong_is_unavailable_with_real_data():
    """실측: 행정동코드 2644059000은 2025-02~2025-12(11개월)만 있어 작년 동기
    (2024-10~12) 데이터가 없다 — 실제 CSV로 이 케이스가 여전히 유효한지 확인."""
    fit = estimate_trend_fit("2644059000", "카페")
    assert fit.data_available is False


def test_known_dong_with_full_history_computes_real_trend():
    """실측: 남포동(2611058000)은 36개월 전체 이력이 있어 정상적으로 계산돼야 한다."""
    fit = estimate_trend_fit("2611058000", "카페")
    assert fit.data_available is True
    assert fit.dong_yoy_pct is not None
    assert fit.city_median_yoy_pct is not None
    assert fit.label
