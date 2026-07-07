from fastapi import APIRouter, HTTPException

from app.data_provider import get_data_provider
from app.data_provider.base import DataProvider
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    BulkScoreResponse,
    RegionInfo,
    RegionScoreSummary,
)
from app.scoring import compute_score

router = APIRouter(prefix="/api", tags=["analyze"])


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

    try:
        market_data = provider.get_market_data(req.region_id, req.category)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    score = compute_score(market_data, req.category)

    return AnalyzeResponse(
        region=market_data.region,
        category=req.category,
        score=score,
        market_data=market_data,
    )
