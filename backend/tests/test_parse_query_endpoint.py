from app.api import analyze as analyze_module
from app.schemas import QueryParseRequest


def _region(region_id, name):
    from app.schemas import RegionInfo

    return RegionInfo(
        region_id=region_id,
        행정동코드=region_id,
        행정동명=name,
        시도명="부산광역시",
        시군구명="테스트구",
        위도=35.1,
        경도=129.0,
    )


def _stub_regions(monkeypatch, regions):
    class _StubProvider:
        def list_regions(self):
            return regions

    monkeypatch.setattr(analyze_module, "get_data_provider", lambda: _StubProvider())


def test_exact_match_needs_no_clarification(monkeypatch):
    regions = [_region("1", "중구 남포동"), _region("2", "부산진구 부전2동")]
    _stub_regions(monkeypatch, regions)
    monkeypatch.setattr(
        analyze_module,
        "parse_query",
        lambda query, names, cats: {"matched_region_names": ["중구 남포동"], "category": "카페"},
    )

    result = analyze_module.parse_query_endpoint(QueryParseRequest(query="남포동에 카페 어때?"))

    assert result.needs_clarification is False
    assert result.category == "카페"
    assert [r.행정동명 for r in result.region_matches] == ["중구 남포동"]
    assert "남포동" in result.message and "카페" in result.message


def test_ambiguous_regions_needs_clarification(monkeypatch):
    regions = [_region("1", "부산진구 부전1동"), _region("2", "부산진구 부전2동")]
    _stub_regions(monkeypatch, regions)
    monkeypatch.setattr(
        analyze_module,
        "parse_query",
        lambda query, names, cats: {
            "matched_region_names": ["부산진구 부전1동", "부산진구 부전2동"],
            "category": "카페",
        },
    )

    result = analyze_module.parse_query_endpoint(QueryParseRequest(query="서면에 카페 어때?"))

    assert result.needs_clarification is True
    assert len(result.region_matches) == 2
    assert "여러 곳" in result.message


def test_no_region_match_needs_clarification(monkeypatch):
    _stub_regions(monkeypatch, [_region("1", "중구 남포동")])
    monkeypatch.setattr(
        analyze_module, "parse_query", lambda query, names, cats: {"matched_region_names": [], "category": "카페"}
    )

    result = analyze_module.parse_query_endpoint(QueryParseRequest(query="서면에 카페 어때?"))

    assert result.needs_clarification is True
    assert result.region_matches == []
    assert "정확히 어디" in result.message


def test_unclear_category_needs_clarification(monkeypatch):
    regions = [_region("1", "부산진구 부전1동")]
    _stub_regions(monkeypatch, regions)
    monkeypatch.setattr(
        analyze_module,
        "parse_query",
        lambda query, names, cats: {"matched_region_names": ["부산진구 부전1동"], "category": None},
    )

    result = analyze_module.parse_query_endpoint(QueryParseRequest(query="부전동에 헬스장 어때?"))

    assert result.needs_clarification is True
    assert result.category is None
    assert len(result.region_matches) == 1
    assert "업종" in result.message


def test_total_failure_falls_back_gracefully(monkeypatch):
    _stub_regions(monkeypatch, [_region("1", "중구 남포동")])

    def _raise(query, names, cats):
        raise RuntimeError("boom")

    monkeypatch.setattr(analyze_module, "parse_query", _raise)

    result = analyze_module.parse_query_endpoint(QueryParseRequest(query="아무 문장"))

    assert result.needs_clarification is True
    assert result.category is None
    assert result.region_matches == []
