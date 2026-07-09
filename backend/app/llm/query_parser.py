"""
PRD 3.6: 자유 텍스트 질의("서면에 커피숍 차릴 건데 어디가 좋아?")에서 지역과 업종을
추출한다. 여기서 하는 일은 "추출"뿐이다 — 실제 지역이 맞는지 검증하고 점수를
계산하는 건 기존 파이프라인(scoring.py, /api/report)이 그대로 한다.

지역명은 Gemini가 임의로 지어내지 않도록, /api/regions의 실제 행정동명 전체
목록을 프롬프트에 주고 "이 목록에 있는 문자열만 골라라"라고 강제한 뒤, 응답도
다시 한 번 그 목록과 대조해서 검증한다(할루시네이션 방어). "서면"처럼 공식
행정동명이 아닌 생활권 이름도 Gemini의 지리 지식으로 관련 행정동 여러 곳을
고를 수 있게 했다 — 결과가 여러 곳이면 그게 곧 "모호함" 신호가 된다.

업종은 카페/한식/중식/분식/기타음식점/편의점/미용실 7개 중 하나 또는 null만
고르게 해서, category_mapping.py가 이미 알고 있는 값과 항상 맞아떨어지게 한다.
"음식점"은 더 이상 리프 카테고리가 아니라 프론트의 1차 탭일 뿐이라 Gemini가
직접 반환할 일이 없다 — 구체적인 음식 종류 없이 "음식점"이라고만 말한 문장은
프롬프트에서 한식으로 간주하도록 명시한다(가장 흔한 케이스라 기본값으로 무난).
"""

import json
import logging
import os

from google import genai
from google.genai import types

from app.region_aliases import REGION_ALIASES

logger = logging.getLogger(__name__)

# report.py와 같은 이유로 gemini-3.1-flash-lite 사용 (RPD 500, Google 공식 후속 모델)
_MODEL = "gemini-3.1-flash-lite"
_TIMEOUT_MS = 10_000
_MAX_OUTPUT_TOKENS = 1000

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "matched_region_names": {
            "type": "array",
            "items": {"type": "string"},
            "description": "문장이 말하는 상권/동네에 해당하는 행정동명(목록에서 골라야 함). 관련된 곳이 여러 곳이면 전부 포함",
        },
        "category": {"type": "string", "nullable": True},
    },
    "required": ["matched_region_names", "category"],
}


def _build_prompt(query: str, region_names: list[str], categories: list[str]) -> str:
    return (
        "사용자의 자연어 문장에서 언급된 지역과 업종을 추출하세요.\n\n"
        "지역은 반드시 아래 목록에 있는 문자열 그대로만 고르세요. 목록에 없는 "
        "지명을 만들어내지 마세요. \"서면\"처럼 공식 행정동명이 아닌 생활권/번화가 "
        "이름이 나오면, 그 지역과 실제로 겹치는 행정동을 아는 대로 모두 고르세요. "
        "전혀 모르겠으면 빈 배열을 반환하세요.\n"
        f"지역 목록: {json.dumps(region_names, ensure_ascii=False)}\n\n"
        "업종은 반드시 아래 중 하나만 고르거나, 확신이 없으면 null을 반환하세요. "
        "목록에 없는 업종을 만들어내지 마세요. 목록에는 '음식점'이 없습니다 — "
        "한식/중식/분식/기타음식점으로 이미 나뉘어 있습니다. 문장이 구체적인 음식 "
        "종류(중식/분식 등) 없이 그냥 '음식점'이나 '식당'이라고만 말하면 한식으로 "
        "간주하세요(가장 흔한 케이스).\n"
        f"업종 목록: {json.dumps(categories, ensure_ascii=False)}\n\n"
        f'사용자 문장: "{query}"'
    )


def parse_query(query: str, region_names: list[str], categories: list[str]) -> dict:
    """{"matched_region_names": [...], "category": str|None} 반환.

    실패(키 없음/타임아웃/API 에러/빈 응답/JSON 파싱 실패)는 예외로 그대로
    올린다 — 호출부(API 엔드포인트)가 "파악하지 못했다"는 사용자 안내로
    바꿔서 처리한다."""
    stripped = query.strip()
    if stripped in REGION_ALIASES:
        # 문장 없이 생활권 이름 단어 하나만 온 경우 — Gemini를 부르지 않고 바로
        # 매칭한다. 업종 정보가 있을 수 없는 입력이라 category는 항상 None이고,
        # region_aliases.py 덕분에 검색창(regionAliases.js)과 항상 같은 결과가
        # 나온다(Gemini는 호출할 때마다 2~4곳 사이로 판단이 갈렸었다).
        fragments = REGION_ALIASES[stripped]
        matched = [name for name in region_names if any(fragment in name for fragment in fragments)]
        return {"matched_region_names": matched, "category": None}

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되어 있지 않음")

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=_TIMEOUT_MS))

    response = client.models.generate_content(
        model=_MODEL,
        contents=_build_prompt(query, region_names, categories),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            temperature=0.1,  # 추출 작업이라 창의성보다 일관성이 중요
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    if not response.text:
        raise RuntimeError("Gemini 응답이 비어 있음")

    parsed = json.loads(response.text)

    region_name_set = set(region_names)
    matched_region_names = [
        name for name in parsed.get("matched_region_names", []) if name in region_name_set
    ]
    dropped = set(parsed.get("matched_region_names", [])) - region_name_set
    if dropped:
        logger.warning("Gemini가 목록에 없는 지역명을 반환해 제외함: %s", dropped)

    category = parsed.get("category")
    if category not in categories:
        category = None

    return {"matched_region_names": matched_region_names, "category": category}
