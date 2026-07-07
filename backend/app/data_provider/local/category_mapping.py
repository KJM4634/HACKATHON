"""
사용자 선택 업종("카페"/"음식점"/"편의점"/"미용실") -> 각 원본 데이터의 실제
분류값 매핑. mock_provider.py의 _CATEGORY_TO_INDUSTRY_LABEL과 동일한 실측
근거(카페 133/음식점 507/편의점 53/미용실 298건, 서면 기준)로 검증된 값이다.
"""

# 상가(상권)정보 표준산업분류명.str.contains(keyword) 로 경쟁업체 필터링
CATEGORY_TO_SANGGABU_KEYWORD: dict[str, str] = {
    "카페": "커피",
    "음식점": "한식",
    "편의점": "편의점",
    "미용실": "미용업",
}

# 일반음식점표준데이터 업태구분명. None이면 이 업종은 폐업 이력 데이터가 없음 —
# 카페(휴게음식점)/편의점(소매업)/미용실(서비스업)은 "일반음식점" 인허가와는
# 다른 카테고리라 이 데이터셋에 포함되지 않는다.
CATEGORY_TO_RESTAURANT_UPTAE: dict[str, str | None] = {
    "카페": None,
    "음식점": "한식",
    "편의점": None,
    "미용실": None,
}
