from fastapi import APIRouter, HTTPException

from app.data_provider import get_data_provider
from app.data_provider.base import DataProvider
from app.schemas import AnalyzeRequest, AnalyzeResponse, RegionInfo
from app.scoring import compute_score

router = APIRouter(prefix="/api", tags=["analyze"])


@router.get("/regions", response_model=list[RegionInfo])
def list_regions() -> list[RegionInfo]:
    provider: DataProvider = get_data_provider()
    return provider.list_regions()


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
