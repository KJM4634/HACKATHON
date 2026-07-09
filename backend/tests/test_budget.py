from app.budget import estimate_budget_fit


def test_high_budget_low_profitability_is_flagged_as_burden():
    fit = estimate_budget_fit(2_000_000, 20)
    assert fit.monthly_budget_krw == 2_000_000
    assert "부담될 수 있습니다" in fit.label


def test_low_budget_high_profitability_is_flagged_as_comfortable():
    fit = estimate_budget_fit(300_000, 90)
    assert "여유있는 편" in fit.label


def test_matched_budget_and_profitability_is_similar_level():
    fit = estimate_budget_fit(1_000_000, 50)
    assert "비슷한 수준" in fit.label


def test_boundary_values_do_not_raise():
    for budget in (300_000, 700_000, 1_500_000, 10_000_000):
        for profitability in (0, 40, 70, 100):
            fit = estimate_budget_fit(budget, profitability)
            assert fit.label


def test_unrealistically_low_budget_is_flagged_unreliable():
    fit = estimate_budget_fit(100_000, 50)
    assert fit.is_unreliable is True
    assert "신뢰도가 낮을 수 있습니다" in fit.label


def test_unrealistically_high_budget_is_flagged_unreliable():
    fit = estimate_budget_fit(50_000_000, 50)
    assert fit.is_unreliable is True
    assert "신뢰도가 낮을 수 있습니다" in fit.label


def test_boundary_values_are_still_reliable():
    """30만원/1,000만원 경계값 자체는 아직 정상 범위로 취급해야 한다(미만/초과만 걸러짐)."""
    assert estimate_budget_fit(300_000, 50).is_unreliable is False
    assert estimate_budget_fit(10_000_000, 50).is_unreliable is False


def test_normal_budget_is_not_flagged_unreliable():
    fit = estimate_budget_fit(1_500_000, 50)
    assert fit.is_unreliable is False
