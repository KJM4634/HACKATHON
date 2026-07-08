import json

from app.llm import query_parser


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, text):
        self._text = text

    def generate_content(self, **kwargs):
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text, **kwargs):
        self.models = _FakeModels(text)


_REGION_NAMES = ["부산진구 부전1동", "부산진구 부전2동", "부산진구 전포동", "중구 남포동"]
_CATEGORIES = ["카페", "음식점", "편의점", "미용실"]


def _mock_gemini(monkeypatch, response_dict):
    monkeypatch.setattr(
        query_parser.genai, "Client", lambda **kwargs: _FakeClient(json.dumps(response_dict, ensure_ascii=False))
    )


def test_parse_query_exact_match(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    _mock_gemini(monkeypatch, {"matched_region_names": ["중구 남포동"], "category": "카페"})

    result = query_parser.parse_query("남포동에 카페 하나 내려는데 어때?", _REGION_NAMES, _CATEGORIES)

    assert result == {"matched_region_names": ["중구 남포동"], "category": "카페"}


def test_parse_query_ambiguous_multiple_regions(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    _mock_gemini(
        monkeypatch,
        {
            "matched_region_names": ["부산진구 부전1동", "부산진구 부전2동", "부산진구 전포동"],
            "category": "카페",
        },
    )

    result = query_parser.parse_query("서면에 커피숍 차릴 건데 어디가 좋아?", _REGION_NAMES, _CATEGORIES)

    assert len(result["matched_region_names"]) == 3
    assert result["category"] == "카페"


def test_parse_query_filters_out_hallucinated_region_names(monkeypatch):
    """목록에 없는 지명을 Gemini가 지어내도 그대로 믿지 않고 걸러내야 한다."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    _mock_gemini(
        monkeypatch,
        {"matched_region_names": ["중구 남포동", "존재하지않는동"], "category": "카페"},
    )

    result = query_parser.parse_query("남포동 근처에 카페 차리고 싶어", _REGION_NAMES, _CATEGORIES)

    assert result["matched_region_names"] == ["중구 남포동"]


def test_parse_query_rejects_unknown_category(monkeypatch):
    """카테고리 목록에 없는 값(예: 헬스장)이 오면 None으로 처리해야 한다."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    _mock_gemini(monkeypatch, {"matched_region_names": ["부산진구 부전1동"], "category": "헬스장"})

    result = query_parser.parse_query("부전동에 헬스장 차리면 어때?", _REGION_NAMES, _CATEGORIES)

    assert result["category"] is None
    assert result["matched_region_names"] == ["부산진구 부전1동"]


def test_parse_query_no_match_returns_empty(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    _mock_gemini(monkeypatch, {"matched_region_names": [], "category": None})

    result = query_parser.parse_query("완전히 관계없는 문장입니다", _REGION_NAMES, _CATEGORIES)

    assert result == {"matched_region_names": [], "category": None}


def test_parse_query_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    try:
        query_parser.parse_query("서면에 카페", _REGION_NAMES, _CATEGORIES)
        assert False, "예외가 발생해야 함"
    except RuntimeError as e:
        assert "GEMINI_API_KEY" in str(e)


_SEOMYEON_REGION_NAMES = [
    "부산진구 부전1동",
    "부산진구 부전2동",
    "부산진구 전포1동",
    "부산진구 전포2동",
    "중구 남포동",
]


def _fail_if_gemini_called(**kwargs):
    raise AssertionError("별칭 단어만 왔을 때는 Gemini를 호출하면 안 됨")


def test_parse_query_bare_alias_word_skips_gemini(monkeypatch):
    """'서면'처럼 별칭 테이블에 있는 단어만 오면 Gemini를 부르지 않고 바로 매칭해야
    한다. GEMINI_API_KEY도 필요 없다는 걸 보여주려고 일부러 지워둔다."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(query_parser.genai, "Client", _fail_if_gemini_called)

    result = query_parser.parse_query("서면", _SEOMYEON_REGION_NAMES, _CATEGORIES)

    assert result["category"] is None
    assert set(result["matched_region_names"]) == {
        "부산진구 부전1동",
        "부산진구 부전2동",
        "부산진구 전포1동",
        "부산진구 전포2동",
    }


def test_parse_query_alias_word_with_surrounding_whitespace(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(query_parser.genai, "Client", _fail_if_gemini_called)

    result = query_parser.parse_query("  서면  ", _SEOMYEON_REGION_NAMES, _CATEGORIES)

    assert len(result["matched_region_names"]) == 4


def test_parse_query_sentence_with_alias_still_uses_gemini(monkeypatch):
    """단어 하나가 아니라 문장이면(기존에 잘 되던 경로) 그대로 Gemini를 쓴다."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    _mock_gemini(
        monkeypatch,
        {"matched_region_names": ["부산진구 부전1동", "부산진구 부전2동"], "category": "카페"},
    )

    result = query_parser.parse_query("서면에 카페 어때?", _SEOMYEON_REGION_NAMES, _CATEGORIES)

    assert result["category"] == "카페"
