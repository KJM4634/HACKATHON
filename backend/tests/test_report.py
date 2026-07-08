from app.llm import report as report_module
from app.schemas import (
    AlternativeRegion,
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


def _candidate(행정동명: str, total_score: int, 수익성: int = 40, alternatives=None) -> AnalyzeResponse:
    region = RegionInfo(
        region_id="0000000000",
        행정동코드="0000000000",
        행정동명=행정동명,
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
        foot_traffic=[
            FootTrafficByHour(시간대="00시", 평균주거인구수=0, 평균직장인구수=0, 평균방문인구수=1000)
        ],
        consumption_by_hour=[],
        consumption_by_category=[ConsumptionByCategory(업종대분류="음식/주점", 평균이용금액=1, 평균이용건수=1)],
        competitors=CompetitorSummary(target_category="카페", total_count=10, sample=[]),
        closure_stats=ClosureStats(
            업태구분명="카페",
            영업중_점포수=10,
            최근1년_신규개업_수=1,
            최근1년_폐업_수=1,
            폐업률=9.1,
            data_available=False,
        ),
    )
    score = ScoreResult(
        total_score=total_score,
        breakdown=ScoreBreakdown(배후수요=50, 경쟁강도=50, 접근성=None, 수익성=수익성),
        weights_used=ScoreWeights(배후수요=0.4375, 경쟁강도=0.375, 접근성=0.0, 수익성=0.1875),
        data_limitations=["테스트 한계 사항"],
        is_placeholder=False,
    )
    return AnalyzeResponse(
        region=region, category="카페", score=score, market_data=market_data, alternatives=alternatives or []
    )


def test_generate_report_falls_back_when_llm_raises(monkeypatch):
    def _raise(category, payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(report_module, "_call_gemini", _raise)

    candidates = [_candidate("서면", 70), _candidate("남포동", 40)]
    text, is_fallback = report_module.generate_report("카페", candidates)

    assert is_fallback is True
    assert "서면" in text
    assert "남포동" in text


def test_fallback_report_ranks_by_score_descending():
    candidates = [_candidate("A동", 30), _candidate("B동", 90), _candidate("C동", 60)]
    text = report_module._fallback_report("카페", candidates)

    lines = [line for line in text.splitlines() if "총점" in line]
    assert lines[0].startswith("1. B동")
    assert lines[1].startswith("2. C동")
    assert lines[2].startswith("3. A동")


def test_build_candidate_payload_includes_scores_not_raw_dump():
    candidates = [_candidate("서면", 70, 수익성=0)]
    payload = report_module._build_candidate_payload(candidates)

    assert len(payload) == 1
    entry = payload[0]
    assert entry["total_score"] == 70
    assert entry["breakdown"]["수익성"] == 0
    assert entry["참고_원자료"]["동일업종_경쟁업체수"] == 10
    assert entry["참고_원자료"]["폐업률(%)"] is None  # data_available=False
    assert entry["data_limitations"] == ["테스트 한계 사항"]


def test_generate_report_succeeds_when_llm_returns_text(monkeypatch):
    monkeypatch.setattr(report_module, "_call_gemini", lambda category, payload: "가짜 리포트 본문")

    text, is_fallback = report_module.generate_report("카페", [_candidate("서면", 70)])

    assert is_fallback is False
    assert text == "가짜 리포트 본문"


def _alt(행정동명, score, distance_km, 경쟁강도=80):
    region = RegionInfo(
        region_id="1111111111",
        행정동코드="1111111111",
        행정동명=행정동명,
        시도명="부산광역시",
        시군구명="테스트구",
        위도=35.11,
        경도=129.01,
    )
    breakdown = ScoreBreakdown(배후수요=50, 경쟁강도=경쟁강도, 접근성=None, 수익성=50)
    return AlternativeRegion(region=region, score=score, distance_km=distance_km, breakdown=breakdown)


def test_build_candidate_payload_includes_alternatives_when_present():
    alt = _alt("옆동", 80, 1.2)
    candidates = [_candidate("아쉬운동", 40, alternatives=[alt])]

    payload = report_module._build_candidate_payload(candidates)

    assert payload[0]["대안_지역"] == [
        {"행정동명": "옆동", "total_score": 80, "distance_km": 1.2, "breakdown": alt.breakdown.model_dump()}
    ]


def test_build_candidate_payload_omits_alternatives_key_when_empty():
    payload = report_module._build_candidate_payload([_candidate("괜찮은동", 70)])

    assert "대안_지역" not in payload[0]


def test_fallback_report_mentions_alternatives():
    alt = _alt("옆동", 80, 1.2)
    candidates = [_candidate("아쉬운동", 40, alternatives=[alt])]

    text = report_module._fallback_report("카페", candidates)

    assert "옆동" in text and "80점" in text and "1.2km" in text
