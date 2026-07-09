from fastapi import APIRouter, HTTPException

from app.data_provider import get_data_provider
from app.grid import compute_grid, to_cell_detail, to_grid_response
from app.llm.grid_report import generate_grid_cell_report
from app.schemas import (
    GridCellDetailRequest,
    GridCellDetailResponse,
    GridCellReportRequest,
    GridCellReportResponse,
    GridResponse,
)

router = APIRouter(prefix="/api/grid", tags=["grid"])

# (region_id, category) -> (cells, cell_size_m, 행정동명). GET /api/grid가 이미 한 번
# 계산한 결과를 셀 클릭(POST /api/grid/cell)이 재사용한다 — report.py의 _report_cache와
# 같은 이유(같은 계산 다시 하지 않기). 프로세스 메모리 캐시라 재시작하면 비워진다.
_grid_cache: dict[tuple[str, str], tuple[list, int, str]] = {}

# (region_id, category, cell_id) -> GridCellReportResponse. "AI 해설 보기" 버튼을
# 누를 때만 Gemini를 호출하고, 같은 셀을 다시 누르면 이 캐시를 그대로 돌려준다 —
# 격자가 행정동 하나에 최대 100개 안팎이라 무료 티어 일일 한도를 지키려면 필수.
# report.py와 같은 이유로 is_fallback=True는 캐시하지 않는다(일시적 장애가 풀린 뒤에도
# 기본 문장이 영영 굳어버리는 걸 막기 위함).
_cell_report_cache: dict[tuple[str, str, str], GridCellReportResponse] = {}


def _get_or_compute_cells(region_id: str, category: str) -> tuple[list, int, str]:
    cached = _grid_cache.get((region_id, category))
    if cached is not None:
        return cached

    provider = get_data_provider()
    try:
        region = provider.get_region_info(region_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    try:
        cells, cell_size_m = compute_grid(region_id, category, region.시군구명)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    cached = (cells, cell_size_m, region.행정동명)
    _grid_cache[(region_id, category)] = cached
    return cached


@router.get("", response_model=GridResponse)
def get_grid(region_id: str, category: str) -> GridResponse:
    cells, cell_size_m, 행정동명 = _get_or_compute_cells(region_id, category)
    return to_grid_response(region_id, 행정동명, category, cells, cell_size_m)


@router.post("/cell", response_model=GridCellDetailResponse)
def get_grid_cell_detail(req: GridCellDetailRequest) -> GridCellDetailResponse:
    cells, _, 행정동명 = _get_or_compute_cells(req.region_id, req.category)
    try:
        return to_cell_detail(req.region_id, 행정동명, cells, req.cell_id, req.home_lat, req.home_lng)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/cell/report", response_model=GridCellReportResponse)
def get_grid_cell_report(req: GridCellReportRequest) -> GridCellReportResponse:
    """"AI 해설 보기"를 눌렀을 때만 호출되는 엔드포인트. 셀 클릭(POST /api/grid/cell)과
    분리해둔 이유는 app/llm/grid_report.py 모듈 docstring 참고."""
    cache_key = (req.region_id, req.category, req.cell_id)
    cached = _cell_report_cache.get(cache_key)
    if cached is not None:
        return cached

    cells, _, 행정동명 = _get_or_compute_cells(req.region_id, req.category)
    try:
        detail = to_cell_detail(req.region_id, 행정동명, cells, req.cell_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    report_text, is_fallback = generate_grid_cell_report(
        category=req.category,
        label=detail.label,
        total_score=detail.total_score,
        breakdown=detail.breakdown.model_dump(),
        competitor_count=detail.competitor_count,
        closure_available=detail.closure_available,
        closure_rate=detail.closure_rate,
        closure_sample=detail.closure_sample,
        # "라벨" 없이 거리/점수만 넘긴다 — 대안도 전부 같은 행정동 안 격자라 이름으로는
        # 구분이 안 되고(좌표 기반 셀 ID는 노출하지 않기로 함), 거리로 구분하면 충분하다.
        alternatives=[
            {"total_score": alt.score, "distance_km": alt.distance_km} for alt in detail.alternatives
        ],
    )

    result = GridCellReportResponse(report_text=report_text, is_fallback=is_fallback)
    if not is_fallback:
        _cell_report_cache[cache_key] = result
    return result
