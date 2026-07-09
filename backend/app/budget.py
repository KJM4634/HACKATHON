"""
사용자가 입력한 예상 월세 예산과, 이미 계산된 수익성 점수(0~100, 206개 행정동
실측 분포 기준 상대 위치 — scoring.py 참고)를 교차해 "감당 가능성" 참고 문구를
만든다.

확정적 계산이 아니다. 부산 상가 임대료를 개별 점포 단위로 구할 수 있는 공공
데이터는 없다 — 국토교통부 실거래가(매매만 있고 상업용 임대차는 신고 의무
자체가 없음), 한국부동산원 임대동향조사(주요 상권 20~30곳만 커버하는 인터랙티브
통계 조회 시스템이라 프로그래밍적으로 즉시 확보 불가)를 모두 확인했다. 대신
이 지역의 수익성 점수(상권 규모의 상대적 위치)와 사용자 예산의 대략적인 구간을
교차시키는 쪽을 택했다 — 새로운 "임대료 대비 매출" 계산식을 만들지 않는다.

예산 구간 경계값(70만원/150만원)은 실측 데이터가 아니라, 중소벤처기업부·
소상공인시장진흥공단 "소상공인 실태조사"에서 확인한 부산 지역 평균 임차료(월세
기준)를 앵커로 잡았다 — 2019년 조사 약 101만원(보증부 기준), 2025년 조사 약
99만원으로 두 조사 시점(6년 터울)이 거의 일치해 신뢰도 있는 참고값으로 판단.
이 평균값이 "보통" 구간 중심에 오도록 70만/150만원으로 경계를 잡았다.
"""

from app.schemas import BudgetFit

_BUDGET_LOW_MAX = 700_000  # 70만원 미만 = 낮음
_BUDGET_HIGH_MIN = 1_500_000  # 150만원 이상 = 높음 (부산 소상공인 평균 임차료 ~100만원이 낮음/높음 사이 "보통" 구간에 위치)

_PROFIT_LOW_MAX = 40  # 수익성 40점 미만 = 상권 규모 작은 편
_PROFIT_HIGH_MIN = 70  # 수익성 70점 이상 = 상권 규모 큰 편


def _budget_rank(monthly_budget_krw: int) -> int:
    if monthly_budget_krw < _BUDGET_LOW_MAX:
        return 0
    if monthly_budget_krw < _BUDGET_HIGH_MIN:
        return 1
    return 2


def _profitability_rank(profitability_score: int) -> int:
    if profitability_score < _PROFIT_LOW_MAX:
        return 0
    if profitability_score < _PROFIT_HIGH_MIN:
        return 1
    return 2


def estimate_budget_fit(monthly_budget_krw: int, profitability_score: int) -> BudgetFit:
    """예산 구간과 수익성 구간의 차이만 본다 — 둘 다 낮으면/둘 다 높으면 "비슷한
    수준", 예산 구간이 수익성 구간보다 높으면 "부담될 수 있음", 낮으면 "여유있는
    편"으로 판단한다."""
    diff = _budget_rank(monthly_budget_krw) - _profitability_rank(profitability_score)
    if diff <= -1:
        label = "이 지역 상권 규모에 비해 예산은 여유있는 편일 수 있습니다"
    elif diff == 0:
        label = "이 지역 상권 규모와 예산이 비슷한 수준으로 보입니다"
    else:
        label = "이 지역 상권 규모 대비 예산이 다소 부담될 수 있습니다"
    return BudgetFit(monthly_budget_krw=monthly_budget_krw, label=label)
