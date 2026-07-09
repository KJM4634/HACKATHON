# backend/app/api/grid_report.py
from fastapi import APIRouter, HTTPException
from app.data_provider import get_data_provider
from app.grid import compute_grid, to_cell_detail
from app.llm.grid_report import generate_grid_cell_report
from app.llm.review_analyzer import generate_review_summary
from app.schemas import GridCellReportRequest, GridCellReportResponse

router = APIRouter(prefix="/api/grid", tags=["grid"])

@router.post("/report", response_model=GridCellReportResponse)
def get_grid_cell_report(req: GridCellReportRequest):
    provider = get_data_provider()
    
    # 1. 지역 정보 조회
    region_info = next((r for r in provider.list_regions() if r.region_id == req.region_id), None)
    if not region_info:
        raise HTTPException(status_code=404, detail="지역 정보를 찾을 수 없습니다.")

    # 2. 격자 데이터 계산
    cells, _ = compute_grid(req.region_id, req.category, region_info.시군구명)
    
    # 3. 상세 정보 조회 (순수 행정동명 가져오기 위함)
    try:
        detail = to_cell_detail(req.region_id, region_info.행정동명, cells, req.cell_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 4. 제미나이를 통한 격자 숫자 해설 (AI 리포트) 생성
    # fallback을 대비해 안전하게 dictionary로 변환하여 전달
    alts = [{"라벨": a.region.행정동명, "total_score": a.score} for a in detail.alternatives]
    
    gemini_text, is_fallback = generate_grid_cell_report(
        category=req.category,
        label=detail.label,
        total_score=detail.total_score,
        breakdown=detail.breakdown.model_dump(),
        competitor_count=detail.competitor_count,
        closure_available=detail.closure_available,
        closure_rate=detail.closure_rate,
        closure_sample=detail.closure_sample,
        alternatives=alts
    )

    # 5. 네이버 블로그 리뷰 요약 (detail.행정동명 활용!)
    review_summary = generate_review_summary(detail.행정동명, req.category)
    
    # 6. 두 텍스트 합치기
    final_text = gemini_text
    if review_summary:
        final_text += f"\n\n{review_summary}"

    return GridCellReportResponse(
        report_text=final_text,
        is_fallback=is_fallback
    )