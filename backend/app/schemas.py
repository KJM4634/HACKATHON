"""
도메인 모델 정의.

필드명은 data_inventory.md에서 확인한 실제 원본 데이터의 컬럼명을 최대한 그대로 사용한다.
(4단계에서 MockDataProvider -> LocalDataProvider로 교체할 때 데이터 매핑 코드를 최소화하기 위함)

매핑 대상 원본 데이터:
- PopulationStats            <- 부울경_행정동별_주민등록_인구_및_세대현황/*.csv (시군구 단위)
- FootTrafficByHour          <- 일별 행정동 시간 생활인구 월별 일평균.csv
- ConsumptionByHour          <- 일별 행정동 시간 소비매출 월별 일평균.csv
- ConsumptionByCategory      <- 일별 행정동 업종 소비매출 월별 일평균.csv
- CompetitorBusiness         <- 소상공인시장진흥공단_상가(상권)정보_*.csv
- ClosureStats               <- 부울경_일반음식점표준데이터/식품_일반음식점_*.csv (인허가일자/폐업일자/영업상태명 집계)
"""

from pydantic import BaseModel, Field


class RegionInfo(BaseModel):
    region_id: str = Field(..., description="서비스 내부 지역 식별자 (예: seomyeon)")
    행정동코드: str = Field(..., description="행정안전부 행정동코드 (생활인구/소비매출 데이터 조인 키)")
    행정동명: str = Field(..., description="예: '부산진구 부전2동'")
    시도명: str
    시군구명: str
    위도: float
    경도: float


class PopulationStats(BaseModel):
    """시군구 단위 주민등록 인구·세대 현황 (행정동보다 큰 단위임에 주의)."""

    기준연도: int
    총인구수: int
    세대수: int
    세대당_인구: float
    남자_인구수: int
    여자_인구수: int
    is_gu_level_estimate: bool = Field(
        True, description="True면 행정동 실측치가 아니라 소속 시군구 전체 값을 그대로 적용한 추정치"
    )


class FootTrafficByHour(BaseModel):
    """시간대별 생활인구 (통신사 신호데이터 기반)."""

    시간대: str = Field(..., description="'00시'~'23시'")
    평균주거인구수: int
    평균직장인구수: int
    평균방문인구수: int


class ConsumptionByHour(BaseModel):
    """시간대별 카드 소비매출."""

    시간대: str
    평균이용금액: int
    평균이용건수: int


class ConsumptionByCategory(BaseModel):
    """업종대분류별 카드 소비매출."""

    업종대분류: str
    평균이용금액: int
    평균이용건수: int


class CompetitorBusiness(BaseModel):
    """경쟁업체 개별 레코드 (지도 마커 표시용 샘플)."""

    상호명: str
    상권업종대분류명: str
    상권업종중분류명: str
    상권업종소분류명: str | None = None
    표준산업분류명: str
    경도: float
    위도: float
    도로명주소: str | None = None


class CompetitorSummary(BaseModel):
    """업종 밀집도(경쟁강도) 산출에 사용할 경쟁업체 요약."""

    target_category: str = Field(..., description="사용자가 선택한 업종")
    total_count: int = Field(..., description="해당 행정동 내 동일업종 전체 업체 수 (밀집도 지표)")
    sample: list[CompetitorBusiness] = Field(default_factory=list, description="지도 표시용 샘플 (최대 20개)")


class ClosureStats(BaseModel):
    """개폐업 현황 (경쟁강도·최근 폐업률 산출용)."""

    업태구분명: str
    영업중_점포수: int
    최근1년_신규개업_수: int
    최근1년_폐업_수: int
    폐업률: float = Field(..., description="최근1년_폐업_수 / (영업중_점포수 + 최근1년_폐업_수) * 100, 단위 %")
    data_available: bool = Field(
        True,
        description="False면 폐업률을 신뢰할 수 없어 0으로 채워진 자리채움값임. 이유는 둘 중 하나: "
        "(1) 일반음식점표준데이터가 이 업종을 다루지 않음(카페/편의점/미용실은 다른 인허가 카테고리) "
        "(2) 음식점 서브카테고리인데 이 지역의 표본이 5건 미만(영업중_점포수+최근1년_폐업_수 참고)",
    )


class MarketData(BaseModel):
    """DataProvider가 반환하는 지역+업종 단위 상권 데이터 묶음. 스코어링 엔진과 LLM 리포트의 입력 재료."""

    region: RegionInfo
    population: PopulationStats
    foot_traffic: list[FootTrafficByHour]
    consumption_by_hour: list[ConsumptionByHour]
    consumption_by_category: list[ConsumptionByCategory]
    competitors: CompetitorSummary
    closure_stats: ClosureStats


class ScoreBreakdown(BaseModel):
    """PRD 3.3 Track B 가중합 항목별 0~100 정규화 점수.

    접근성은 대중교통/집객시설 근접도 데이터가 없어 계산하지 않는다(None).
    실제로 적용된 가중치는 ScoreResult.weights_used를 봐야 한다."""

    배후수요: int = Field(..., ge=0, le=100)
    경쟁강도: int = Field(..., ge=0, le=100)
    접근성: int | None = Field(None, ge=0, le=100, description="데이터 없어 미계산")
    수익성: int = Field(..., ge=0, le=100)


class ScoreWeights(BaseModel):
    """이번 산출에 실제로 적용된 가중치 (합계 1.0). PRD 원안은 0.35/0.3/0.2/0.15."""

    배후수요: float
    경쟁강도: float
    접근성: float
    수익성: float


class TrackAPrediction(BaseModel):
    """PRD 3.3 Track A: 실제 라벨(인허가일자/폐업일자)로 학습한 폐업위험 예측.
    현재 '음식점(한식)'만 실제 라벨이 있어 학습됨 — 다른 업종은 available=False."""

    available: bool = Field(..., description="이 업종에 실제 라벨로 학습된 Track A 모델이 있는지")
    closure_risk_3yr: float | None = Field(
        None, ge=0, le=1, description="3년 내 폐업 확률 예측치(0~1). available=False면 None"
    )
    model_name: str | None = Field(None, description="사용된 모델 이름 (예: random_forest)")


class ScoreResult(BaseModel):
    total_score: int = Field(..., ge=0, le=100, description="0~100 생존/성공 스코어")
    breakdown: ScoreBreakdown
    weights_used: ScoreWeights
    data_limitations: list[str] = Field(
        default_factory=list, description="데이터 부족으로 근사/제외/재분배한 지표에 대한 설명"
    )
    is_placeholder: bool = Field(
        False, description="True면 고정값(스코어링 로직 미구현 상태)."
    )
    track_a: TrackAPrediction = Field(
        default_factory=lambda: TrackAPrediction(available=False),
        description="PRD 3.3 Track A 예측 (실제 라벨 학습 모델이 있는 업종만 채워짐)",
    )


class AnalyzeRequest(BaseModel):
    region_id: str = Field(..., description="지역 식별자 (현재는 Mock 프리셋 목록 중 하나)")
    category: str = Field(..., description="사용자가 선택한 업종 (예: '카페')")


class AlternativeRegion(BaseModel):
    """이 지역보다 점수가 높고 가까운(3km 이내) 대안 후보."""

    region: RegionInfo
    score: int = Field(..., ge=0, le=100)
    distance_km: float = Field(..., ge=0)
    breakdown: ScoreBreakdown = Field(
        ..., description="LLM이 '구체적으로 왜 더 나은지' 지어내지 않고 실제 지표로 말할 수 있게 제공"
    )


class AnalyzeResponse(BaseModel):
    region: RegionInfo
    category: str
    score: ScoreResult
    market_data: MarketData
    alternatives: list[AlternativeRegion] = Field(
        default_factory=list,
        description="총점이 낮을 때(app.alternatives.LOW_SCORE_THRESHOLD 이하) 채워지는 인근 대안 후보. 평소엔 빈 리스트",
    )
    differentiation_strategy: str | None = Field(
        None,
        description="총점이 낮을 때 Gemini가 제안하는 차별화 전략(참고용, 확정적 조언 아님). "
        "alternatives와 같은 조건에서만 채워지고, Gemini 실패 시에도 None(억지 대체 문구 없음)",
    )


class RegionScoreSummary(BaseModel):
    """지도 색상 표시용 요약 — 지역 하나당 가벼운 점수 정보만."""

    region_id: str
    total_score: int
    is_gu_level_estimate: bool = Field(
        ..., description="True면 배후인구가 구 단위 추정치 — 지도에서 낮은 신뢰도로 표시"
    )


class BulkScoreResponse(BaseModel):
    category: str
    scores: list[RegionScoreSummary]


class ReportRequest(BaseModel):
    region_ids: list[str] = Field(
        ..., min_length=1, max_length=10, description="비교할 후보 지역 (1~10곳)"
    )
    category: str = Field(..., description="사용자가 선택한 업종 (예: '카페')")
    include_alternatives: bool = Field(
        True, description="True면 점수가 낮은 후보에 대해 인근 대안 지역을 찾아 리포트에 비교 반영"
    )


class ReportResponse(BaseModel):
    category: str
    candidates: list[AnalyzeResponse] = Field(..., description="LLM에 넘긴 후보별 점수+원자료")
    report_text: str
    is_fallback: bool = Field(
        ..., description="True면 LLM 호출 실패/시간초과로 점수만으로 만든 기본 템플릿 리포트"
    )


class QueryParseRequest(BaseModel):
    query: str = Field(..., min_length=1, description="자연어 질의 (예: '서면에 커피숍 차릴 건데 어디가 좋아?')")


class QueryParseResponse(BaseModel):
    category: str | None = Field(None, description="추출된 업종. 확신 없으면 None")
    region_matches: list[RegionInfo] = Field(
        default_factory=list, description="/api/regions 목록과 대조해 검증된 지역 후보. 0곳=매칭 실패, 2곳 이상=모호함"
    )
    needs_clarification: bool = Field(
        ..., description="True면 업종 미확정이거나 지역이 0곳/2곳 이상이라 사용자 확인이 필요함"
    )
    message: str = Field(..., description="사용자에게 보여줄 안내 문구")


class GridCellBounds(BaseModel):
    """지도에 사각형(L.rectangle)을 그리기 위한 경계."""

    north: float
    south: float
    east: float
    west: float


class GridCellSummary(BaseModel):
    """격자 지도 색칠용 — 셀 하나당 가벼운 점수 정보만 (app/grid.py 참고)."""

    cell_id: str
    center_위도: float
    center_경도: float
    bounds: GridCellBounds
    total_score: int
    breakdown: ScoreBreakdown


class GridResponse(BaseModel):
    region_id: str = Field(..., description="이 격자가 속한 행정동의 region_id")
    행정동명: str
    category: str
    cell_size_m: int = Field(..., description="이 행정동에 맞춰 고른 격자 한 변의 길이(m) — 100/250/500/1000 중 하나")
    cells: list[GridCellSummary]


class GridCellDetailRequest(BaseModel):
    region_id: str
    category: str
    cell_id: str


class GridCellDetailResponse(BaseModel):
    """격자 셀 상세 패널용. Track A는 행정동 단위로 학습된 모델이라 격자에는
    적용하지 않는다(available=False 고정). AI 해설(Gemini 리포트)은 셀 클릭 시
    자동으로 만들지 않고 — 격자가 행정동 하나에 최대 100개 안팎이라 자동 호출이면
    무료 티어 일일 한도를 금방 씀 — 이 응답에는 숫자 기반 게이지/막대바/대안만
    담는다. AI 해설은 사용자가 "AI 해설 보기"를 눌렀을 때만 GridCellReportRequest로
    별도 요청한다(app/llm/grid_report.py)."""

    cell_id: str
    label: str = Field(..., description="예: '부산진구 부전2동 (격자 B-4)'")
    행정동명: str = Field(..., description="순수 행정동명 (검색/리뷰용)")
    total_score: int
    breakdown: ScoreBreakdown
    competitor_count: int
    closure_available: bool
    closure_rate: float
    closure_sample: int = Field(..., description="영업중_점포수 + 최근1년_폐업_수")
    data_limitations: list[str]
    alternatives: list[AlternativeRegion] = Field(
        default_factory=list, description="같은 행정동 내에서 점수가 더 높은 다른 격자 (최대 3곳)"
    )


class GridCellReportRequest(BaseModel):
    region_id: str
    category: str
    cell_id: str


class GridCellReportResponse(BaseModel):
    """"AI 해설 보기"를 눌렀을 때만 요청하는 격자 셀 해설. (region_id, category,
    cell_id) 키로 캐싱되어 같은 셀을 다시 눌러도 Gemini를 재호출하지 않는다."""

    report_text: str
    is_fallback: bool = Field(..., description="True면 LLM 호출 실패로 점수 기반 기본 문장으로 대체")
