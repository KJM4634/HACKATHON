from app.llm import strategy as strategy_module
from app.schemas import (
    AnalyzeResponse,
    ClosureStats,
    CompetitorSummary,
    ConsumptionByCategory,
    FootTrafficByHour,
    MarketData,
    PopulationStats,
    RegionInfo,
    ScoreBreakdown,
    ScoreResult,
    ScoreWeights,
)


def _candidate(total_score=40, 경쟁강도=10, closure_available=True, 폐업률=9.1):
    region = RegionInfo(
        region_id="0000000000",
        행정동코드="0000000000",
        행정동명="아쉬운동",
        시도명="부산광역시",
        시군구명="테스트구",
        위도=35.1,
        경도=129.0,
    )
    market_data = MarketData(
        region=region,
        population=PopulationStats(
            기준연도=2025, 총인구수=100000, 세대수=1, 세대당_인구=1.0, 남자_인구수=1, 여자_인구수=1
        ),
        foot_traffic=[FootTrafficByHour(시간대="00시", 평균주거인구수=0, 평균직장인구수=0, 평균방문인구수=1000)],
        consumption_by_hour=[],
        consumption_by_category=[ConsumptionByCategory(업종대분류="음식/주점", 평균이용금액=1, 평균이용건수=1)],
        competitors=CompetitorSummary(target_category="카페", total_count=76, sample=[]),
        closure_stats=ClosureStats(
            업태구분명="카페",
            영업중_점포수=10,
            최근1년_신규개업_수=1,
            최근1년_폐업_수=1,
            폐업률=폐업률,
            data_available=closure_available,
        ),
    )
    score = ScoreResult(
        total_score=total_score,
        breakdown=ScoreBreakdown(배후수요=50, 경쟁강도=경쟁강도, 접근성=None, 수익성=40),
        weights_used=ScoreWeights(배후수요=0.4375, 경쟁강도=0.375, 접근성=0.0, 수익성=0.1875),
        data_limitations=[],
        is_placeholder=False,
    )
    return AnalyzeResponse(region=region, category="카페", score=score, market_data=market_data)


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, text):
        self._text = text

    def generate_content(self, **kwargs):
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text, **kwargs):
        self.models = _FakeModels(text)


def test_build_payload_includes_score_and_competitor_data():
    candidate = _candidate(total_score=40, 경쟁강도=10)

    payload = strategy_module._build_payload(candidate)

    assert payload["total_score"] == 40
    assert payload["breakdown"]["경쟁강도"] == 10
    assert payload["동일업종_경쟁업체수"] == 76
    assert payload["폐업률(%)"] == 9.1


def test_build_payload_omits_closure_rate_when_unavailable():
    candidate = _candidate(closure_available=False)

    payload = strategy_module._build_payload(candidate)

    assert payload["폐업률(%)"] is None


def test_generate_differentiation_strategy_succeeds(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(
        strategy_module.genai, "Client", lambda **kwargs: _FakeClient("경쟁이 치열하니 틈새 메뉴를 고려해보세요.")
    )

    result = strategy_module.generate_differentiation_strategy(_candidate())

    assert result == "경쟁이 치열하니 틈새 메뉴를 고려해보세요."


def test_generate_differentiation_strategy_returns_none_without_fallback_text(monkeypatch):
    """report.py의 비교 리포트와 달리, 실패해도 점수 기반 대체 문구를 지어내지
    않고 그냥 None이어야 한다 — 창작 조언은 억지로 템플릿화할 근거가 없다."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = strategy_module.generate_differentiation_strategy(_candidate())

    assert result is None


def test_generate_differentiation_strategy_returns_none_on_gemini_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def _raise(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(strategy_module.genai, "Client", _raise)

    result = strategy_module.generate_differentiation_strategy(_candidate())

    assert result is None
