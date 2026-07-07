from fastapi import APIRouter, HTTPException

from app.data_provider import get_data_provider
from app.data_provider.base import DataProvider
from app.llm.report import generate_report
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    BulkScoreResponse,
    RegionInfo,
    RegionScoreSummary,
    ReportRequest,
    ReportResponse,
)
from app.scoring import compute_score

router = APIRouter(prefix="/api", tags=["analyze"])


def _analyze_one(provider: DataProvider, region_id: str, category: str) -> AnalyzeResponse:
    try:
        market_data = provider.get_market_data(region_id, category)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    score = compute_score(market_data, category)
    return AnalyzeResponse(
        region=market_data.region,
        category=category,
        score=score,
        market_data=market_data,
    )


@router.get("/regions", response_model=list[RegionInfo])
def list_regions() -> list[RegionInfo]:
    provider: DataProvider = get_data_provider()
    return provider.list_regions()


@router.get("/scores", response_model=BulkScoreResponse)
def bulk_scores(category: str) -> BulkScoreResponse:
    """지도 전체를 색칠하기 위한 전 지역 점수 요약. 지역당 상세 데이터(market_data)는 뺀
    가벼운 버전 — 상세는 /api/analyze로 개별 조회."""
    provider: DataProvider = get_data_provider()

    scores = []
    for region in provider.list_regions():
        market_data = provider.get_market_data(region.region_id, category)
        score = compute_score(market_data, category)
        scores.append(
            RegionScoreSummary(
                region_id=region.region_id,
                total_score=score.total_score,
                is_gu_level_estimate=market_data.population.is_gu_level_estimate,
            )
        )

    return BulkScoreResponse(category=category, scores=scores)


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    provider: DataProvider = get_data_provider()
    return _analyze_one(provider, req.region_id, req.category)


@router.post("/report", response_model=ReportResponse)
def report(req: ReportRequest) -> ReportResponse:
    """PRD 3.4: 후보 지역 여러 곳을 분석해 Top3 추천 입지 + 이유 + 리스크를
    자연어 리포트로 만든다. LLM 실패 시 점수만으로 만든 기본 템플릿으로 대체."""
    provider: DataProvider = get_data_provider()
    candidates = [_analyze_one(provider, region_id, req.category) for region_id in req.region_ids]

    report_text, is_fallback = generate_report(req.category, candidates)

    return ReportResponse(
        category=req.category,
        candidates=candidates,
        report_text=report_text,
        is_fallback=is_fallback,
    )
