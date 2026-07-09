# backend/app/api/grid_report.py
from fastapi import APIRouter, HTTPException
from app.data_provider import get_data_provider
from app.grid import compute_grid, to_cell_detail
from app.llm.grid_report import generate_grid_cell_report
from app.llm.review_analyzer import generate_review_summary
from app.schemas import GridCellReportRequest, GridCellReportResponse

router = APIRouter(prefix="/api/grid", tags=["grid"])

# app/api/grid.py의 _cell_report_cache와 같은 이유로 캐싱한다 — 이 엔드포인트는
# Gemini를 두 번(격자 해설 + 리뷰 요약) 부르고 네이버 API도 호출하므로, 같은 셀을
# 다시 누를 때마다 매번 다시 부르면 무료 티어/일일 한도를 더 빨리 쓴다.
# is_fallback=True는 캐시하지 않는다(일시적 장애가 풀린 뒤에도 기본 문장이
# 영영 굳어버리는 걸 막기 위함 — 기존 캐시들과 같은 규칙).
_review_report_cache: dict[tuple[str, str, str], GridCellReportResponse] = {}


@router.post("/report", response_model=GridCellReportResponse)
def get_grid_cell_report(req: GridCellReportRequest):
    cache_key = (req.region_id, req.category, req.cell_id)
    cached = _review_report_cache.get(cache_key)
    if cached is not None:
        return cached

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
    # "라벨" 없이 거리/점수만 넘긴다 — app/api/grid.py의 기존 엔드포인트와 같은 이유:
    # 대안도 전부 같은 행정동 안 격자라 이름으로는 구분이 안 되고(좌표 기반 셀 ID는
    # 노출하지 않기로 함), 거리로 구분하면 충분하다. llm/grid_report.py의
    # _fallback_report()가 distance_km를 직접 참조하므로 이 키가 항상 있어야 한다.
    alts = [{"total_score": a.score, "distance_km": a.distance_km} for a in detail.alternatives]
    
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

    result = GridCellReportResponse(report_text=final_text, is_fallback=is_fallback)
    if not is_fallback:
        _review_report_cache[cache_key] = result
    return result