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
기준, 2019년 조사 약 101만원, 보증부 기준)를 앵커로 잡았다. (참고: 2025년 조사의
부산 특정 수치로 알려졌던 값은 재확인 결과 임차인 월세가 아니라 임대인의 "연간
총임대수익액"이었고, 부산 월세 자체는 2025년 조사의 지역별 공개표에 아예 없어
근거로 쓰지 않았다 — 2019년 단일 시점 수치에만 의존한다는 한계가 있음.) 이
평균값이 "보통" 구간 중심에 오도록 70만/150만원으로 경계를 잡았다.

입력값 현실성 검증(sanity check): 위 앵커(약 101만원)에서 크게 벗어난 값은
"여유/보통/부담" 판단 자체가 무의미하다 — 예를 들어 월세 10만원을 "여유있는
편"이라고 판단하면, 그 결론이 잘못된 게 아니라 애초에 "정상적인 상가 임대차가
아닐 가능성"을 놓친 것이다. 그래서 판단 전에 입력값이 최소한의 상식 범위
(30만원~1,000만원) 안에 있는지부터 확인한다:
- 하한 30만원: 2019년 조사에서 "보증금 없는" 가장 저렴한 형태의 계약조차 평균
  월세가 82만원이었다 — 이 최저 형태 평균보다도 한참 낮은 30만원 미만은 정상
  상가 임대차로 보기 어렵다(단위 착오, 오타 등 가능성이 더 높음).
- 상한 1,000만원: 부산 평균(~100만원)의 약 10배로, 서면·해운대 등 최상급
  상권의 대형 매장 임대료까지는 이 범위 안에서 커버된다고 보되, 이보다 훨씬 큰
  값은 소상공인(카페·음식점·편의점·미용실) 규모를 벗어난 대형/기업형 임대차로
  보고 참고 판단을 유보한다.
이 범위를 벗어나면 여유/보통/부담 라벨 대신 "신뢰도가 낮다"는 경고만 반환하고,
Gemini 리포트에도 이 경우엔 예산 언급 자체를 넘기지 않는다(app/llm/report.py).
"""

from app.schemas import BudgetFit

_REALISTIC_BUDGET_MIN = 300_000  # 30만원 미만 = 정상적인 상가 임대차로 보기 어려움
_REALISTIC_BUDGET_MAX = 10_000_000  # 1,000만원 초과 = 소상공인 규모를 벗어난 임대차로 봄

_LOW_BUDGET_WARNING = (
    "입력하신 예산이 일반적인 부산 상가 임대 시세보다 많이 낮아, 참고 정보의 신뢰도가 낮을 수 있습니다"
)
_HIGH_BUDGET_WARNING = (
    "입력하신 예산이 일반적인 부산 상가 임대 시세보다 많이 높아, 참고 정보의 신뢰도가 낮을 수 있습니다"
)

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
    편"으로 판단한다. 단, 입력값 자체가 현실적인 범위를 벗어나면(30만원 미만 또는
    1,000만원 초과) 이 판단을 하지 않고 신뢰도 경고만 돌려준다(모듈 docstring
    참고)."""
    if monthly_budget_krw < _REALISTIC_BUDGET_MIN:
        return BudgetFit(monthly_budget_krw=monthly_budget_krw, label=_LOW_BUDGET_WARNING, is_unreliable=True)
    if monthly_budget_krw > _REALISTIC_BUDGET_MAX:
        return BudgetFit(monthly_budget_krw=monthly_budget_krw, label=_HIGH_BUDGET_WARNING, is_unreliable=True)

    diff = _budget_rank(monthly_budget_krw) - _profitability_rank(profitability_score)
    if diff <= -1:
        label = "이 지역 상권 규모에 비해 예산은 여유있는 편일 수 있습니다"
    elif diff == 0:
        label = "이 지역 상권 규모와 예산이 비슷한 수준으로 보입니다"
    else:
        label = "이 지역 상권 규모 대비 예산이 다소 부담될 수 있습니다"
    return BudgetFit(monthly_budget_krw=monthly_budget_krw, label=label)
