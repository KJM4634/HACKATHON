from fastapi import APIRouter, HTTPException

from app.alternatives import LOW_SCORE_THRESHOLD, find_alternatives
from app.data_provider import get_data_provider
from app.data_provider.base import DataProvider
from app.data_provider.local.category_mapping import CATEGORY_TO_SANGGABU_KEYWORD
from app.llm.query_parser import parse_query
from app.llm.report import generate_report
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    BulkScoreResponse,
    QueryParseRequest,
    QueryParseResponse,
    RegionInfo,
    RegionScoreSummary,
    ReportRequest,
    ReportResponse,
)
from app.scoring import compute_score

router = APIRouter(prefix="/api", tags=["analyze"])

_KNOWN_CATEGORIES = list(CATEGORY_TO_SANGGABU_KEYWORD.keys())

# (region_ids 정렬 튜플, category, include_alternatives) -> ReportResponse. 프로세스
# 메모리에만 있는 캐시라 재시작하면 비워진다 — Gemini 무료 티어 일일 한도가 낮아서,
# 같은 조합을 반복 호출할 때(데모 리허설, 새로고침 등) 쿼터를 아끼는 게 목적이다.
# include_alternatives도 키에 넣는 이유: 같은 지역 조합이라도 이 값에 따라 프롬프트에
# 들어가는 내용(대안 비교 섹션 유무)이 달라져 결과가 달라지므로, 빼면 한쪽 호출 결과가
# 다른 쪽에 잘못 재사용될 수 있다.
# is_fallback=True인 결과는 캐시하지 않는다 — 그렇게 하면 일시적 Gemini 장애로 받은
# 기본 템플릿이 장애가 풀린 뒤에도 영영 굳어버린다.
_report_cache: dict[tuple[tuple[str, ...], str, bool], ReportResponse] = {}


def _all_scores_for_category(provider: DataProvider, category: str) -> dict[str, int]:
    """대안 지역을 찾을 때만 쓰는, 206개 행정동 전체의 총점 맵(가벼운 값만)."""
    return {
        region.region_id: compute_score(provider.get_market_data(region.region_id, category), category).total_score
        for region in provider.list_regions()
    }


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
    자연어 리포트로 만든다. LLM 실패 시 점수만으로 만든 기본 템플릿으로 대체.

    점수가 낮은(50점 이하) 후보는 include_alternatives=True일 때 같은 업종·3km
    이내에서 더 점수 높은 대안을 찾아 붙이고, Gemini가 "왜 이 지역이 아쉬운지 +
    대안이 왜 나은지"를 비교해서 설명하게 한다.

    같은 (지역 조합, 업종, include_alternatives)로 이미 성공한 리포트가 있으면
    Gemini를 다시 부르지 않고 그 결과를 그대로 돌려준다(무료 티어 쿼터 절약)."""
    cache_key = (tuple(sorted(req.region_ids)), req.category, req.include_alternatives)
    cached = _report_cache.get(cache_key)
    if cached is not None:
        return cached

    provider: DataProvider = get_data_provider()
    candidates = [_analyze_one(provider, region_id, req.category) for region_id in req.region_ids]

    if req.include_alternatives:
        all_scores: dict[str, int] | None = None
        region_by_id: dict[str, RegionInfo] | None = None
        for candidate in candidates:
            if candidate.score.total_score > LOW_SCORE_THRESHOLD:
                continue
            if all_scores is None:  # 낮은 후보가 있을 때만, 그것도 한 번만 전체를 계산
                all_scores = _all_scores_for_category(provider, req.category)
                region_by_id = {r.region_id: r for r in provider.list_regions()}
            candidate.alternatives = find_alternatives(
                candidate.region, candidate.score.total_score, all_scores, region_by_id
            )

    report_text, is_fallback = generate_report(req.category, candidates)

    result = ReportResponse(
        category=req.category,
        candidates=candidates,
        report_text=report_text,
        is_fallback=is_fallback,
    )
    if not is_fallback:
        _report_cache[cache_key] = result
    return result


@router.post("/parse-query", response_model=QueryParseResponse)
def parse_query_endpoint(req: QueryParseRequest) -> QueryParseResponse:
    """PRD 3.6: 자연어 질의에서 지역/업종을 추출해, 기존 /api/report가 바로 쓸 수 있는
    형태(region_id + category)로 검증해 돌려준다. 새 분석 로직은 없다 — 여기서 하는
    일은 프론트가 기존 검색창/업종선택 상태를 채울 값을 만들어주는 것뿐이다."""
    provider: DataProvider = get_data_provider()
    regions = provider.list_regions()
    region_names = [r.행정동명 for r in regions]

    try:
        parsed = parse_query(req.query, region_names, _KNOWN_CATEGORIES)
    except Exception:
        return QueryParseResponse(
            category=None,
            region_matches=[],
            needs_clarification=True,
            message="문장에서 지역과 업종을 파악하지 못했어요. 아래에서 직접 선택해주세요.",
        )

    name_to_region = {r.행정동명: r for r in regions}
    matches = [name_to_region[name] for name in parsed["matched_region_names"]]
    category = parsed["category"]

    if not matches and category is None:
        message = "지역과 업종을 정확히 파악하지 못했어요. 아래에서 직접 선택해주세요."
    elif not matches:
        message = "정확히 어디를 말씀하시는 건가요? 아래 검색창에서 지역을 선택해주세요."
    elif len(matches) > 1:
        names = ", ".join(m.행정동명 for m in matches)
        message = f'"{req.query}"에 해당하는 지역이 여러 곳이에요 ({names}). 검색창에 원하시는 동 이름을 입력해주세요.'
    elif category is None:
        message = f"{matches[0].행정동명}은(는) 찾았는데, 업종을 정확히 파악하지 못했어요. 위에서 업종을 선택해주세요."
    else:
        message = f"{matches[0].행정동명} · {category}로 분석합니다."

    return QueryParseResponse(
        category=category,
        region_matches=matches,
        needs_clarification=category is None or len(matches) != 1,
        message=message,
    )
