"""
스코어링 엔진 자리. (PRD 3.3 Track B 가중합 예정 위치)

지금은 4단계 스코어링 로직이 들어오기 전까지 입력과 무관하게 고정 점수를 반환한다.
/api/analyze 는 이 함수의 반환값만 보고 동작하므로, 4단계에서 이 함수 내부만
실제 로직(정규화 + 가중합 or ML)으로 바꾸면 나머지 파이프라인은 그대로 재사용된다.
"""

from app.schemas import MarketData, ScoreBreakdown, ScoreResult

# PRD 3.3 Track B 가중치 예시: 배후수요 0.35 + 경쟁강도 0.3(역가중) + 접근성 0.2 + 수익성 0.15
_PLACEHOLDER_BREAKDOWN = ScoreBreakdown(배후수요=25, 경쟁강도=20, 접근성=15, 수익성=10)
_PLACEHOLDER_TOTAL = sum(_PLACEHOLDER_BREAKDOWN.model_dump().values())


def compute_score(market_data: MarketData, category: str) -> ScoreResult:
    """TODO(4단계): market_data + category 기반 실제 가중합/ML 스코어링으로 교체."""
    return ScoreResult(
        total_score=_PLACEHOLDER_TOTAL,
        breakdown=_PLACEHOLDER_BREAKDOWN,
        is_placeholder=True,
    )
