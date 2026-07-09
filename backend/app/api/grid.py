import re
import json
import logging
import os

from fastapi import APIRouter, HTTPException

from app.data_provider import get_data_provider
from app.grid import compute_grid, to_cell_detail, to_grid_response
from app.llm.grid_report import generate_grid_cell_report
from app.llm.review_analyzer import generate_review_summary  # 🚀 네이버 리뷰 함수 import
from app.schemas import (
    GridCellDetailRequest,
    GridCellDetailResponse,
    GridCellReportRequest,
    GridCellReportResponse,
    GridResponse,
)

router = APIRouter(prefix="/api/grid", tags=["grid"])

# (region_id, category) -> (cells, cell_size_m, 행정동명) 캐시
_grid_cache: dict[tuple[str, str], tuple[list, int, str]] = {}

# (region_id, category, cell_id) -> GridCellReportResponse 캐시
_cell_report_cache: dict[tuple[str, str, str], GridCellReportResponse] = {}


def _grid_label_only(label: str) -> str:
    match = re.search(r"격자 [^)]+", label)
    return match.group(0) if match else label


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
        return to_cell_detail(req.region_id, 행정동명, cells, req.cell_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/cell/report", response_model=GridCellReportResponse)
def get_grid_cell_report(req: GridCellReportRequest) -> GridCellReportResponse:
    cache_key = (req.region_id, req.category, req.cell_id)
    cached = _cell_report_cache.get(cache_key)
    if cached is not None:
        return cached

    cells, _, 행정동명 = _get_or_compute_cells(req.region_id, req.category)
    try:
        # 🚀 클로드가 찾아낸 버그 수정: 여기서 행정동명을 넣어주면 detail.행정동명 필드에 순수 이름이 저장됨
        detail = to_cell_detail(req.region_id, 행정동명, cells, req.cell_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    # 원래 잘 돌아가던 제미나이 격자 해설(숫자 요약) 글 받기
    report_text, is_fallback = generate_grid_cell_report(
        category=req.category,
        label=detail.label,
        total_score=detail.total_score,
        breakdown=detail.breakdown.model_dump(),
        competitor_count=detail.competitor_count,
        closure_available=detail.closure_available,
        closure_rate=detail.closure_rate,
        closure_sample=detail.closure_sample,
        alternatives=[
            {"라벨": _grid_label_only(alt.region.행정동명), "total_score": alt.score, "distance_km": alt.distance_km}
            for alt in detail.alternatives
        ],
    )

    # 🚀 [우리의 꼼수 추가] "격자 J-7"이 빠진 순수한 동네 이름(detail.행정동명)으로 네이버 리뷰 요약 불러오기!
    review_summary = generate_review_summary(detail.행정동명, req.category)

    # 두 텍스트를 엔터 두 번 치고 하나로 합체!
    final_text = report_text
    if review_summary:
        final_text += f"\n\n{review_summary}"

    result = GridCellReportResponse(report_text=final_text, is_fallback=is_fallback)
    if not is_fallback:
        _cell_report_cache[cache_key] = result
    return result