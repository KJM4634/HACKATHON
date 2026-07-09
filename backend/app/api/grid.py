from fastapi import APIRouter, HTTPException

from app.data_provider import get_data_provider
from app.grid import compute_grid, to_cell_detail, to_grid_response
from app.schemas import GridCellDetailRequest, GridCellDetailResponse, GridResponse

router = APIRouter(prefix="/api/grid", tags=["grid"])

# (region_id, category) -> (cells, cell_size_m, 행정동명). GET /api/grid가 이미 한 번
# 계산한 결과를 셀 클릭(POST /api/grid/cell)이 재사용한다 — report.py의 _report_cache와
# 같은 이유(같은 계산 다시 하지 않기). 프로세스 메모리 캐시라 재시작하면 비워진다.
_grid_cache: dict[tuple[str, str], tuple[list, int, str]] = {}


@router.get("", response_model=GridResponse)
def get_grid(region_id: str, category: str) -> GridResponse:
    provider = get_data_provider()
    try:
        region = provider.get_region_info(region_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    try:
        cells, cell_size_m = compute_grid(region_id, category, region.시군구명)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    _grid_cache[(region_id, category)] = (cells, cell_size_m, region.행정동명)
    return to_grid_response(region_id, region.행정동명, category, cells, cell_size_m)


@router.post("/cell", response_model=GridCellDetailResponse)
def get_grid_cell_detail(req: GridCellDetailRequest) -> GridCellDetailResponse:
    cached = _grid_cache.get((req.region_id, req.category))
    if cached is None:
        provider = get_data_provider()
        try:
            region = provider.get_region_info(req.region_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        try:
            cells, cell_size_m = compute_grid(req.region_id, req.category, region.시군구명)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        cached = (cells, cell_size_m, region.행정동명)
        _grid_cache[(req.region_id, req.category)] = cached

    cells, _, 행정동명 = cached
    try:
        return to_cell_detail(req.region_id, 행정동명, cells, req.cell_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
