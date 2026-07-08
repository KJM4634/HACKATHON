"""
점수가 낮은(app.alternatives.LOW_SCORE_THRESHOLD 이하) 지역이어도 "그래도 여기서
하고 싶다"는 사용자를 위해, 그 지역의 실제 지표를 근거로 차별화 전략을 제안한다.

report.py의 비교 리포트와는 성격이 달라서(하나는 "여기보다 저기", 이건 "그래도
여기서 어떻게") 별도 파일로 뒀다. 실패해도 report.py처럼 점수 기반 대체 문구를
지어내지 않는다 — "이렇게 하면 된다"는 창작 조언을 억지로 템플릿화할 근거가
없으므로, 실패하면 그냥 이 섹션을 비워둔다(호출부가 None 처리).
"""

import json
import logging
import os

from google import genai
from google.genai import types

from app.schemas import AnalyzeResponse

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.1-flash-lite"
_TIMEOUT_MS = 15_000
_MAX_OUTPUT_TOKENS = 1000

_SYSTEM_INSTRUCTION = """당신은 소상공인 창업 컨설턴트입니다. 사용자 메시지에 특정
지역 하나의 점수·세부지표·경쟁 현황이 JSON으로 주어집니다. 이 지역은 총점이
낮게 나온 곳이지만, 그래도 여기서 창업하고 싶어하는 예비 소상공인을 위해 이
지역의 특성을 살릴 수 있는 차별화 전략을 제안하세요. 다음 규칙을 반드시
지키세요:

1. 점수나 지표를 다시 계산하지 말고 주어진 숫자를 그대로 근거로 인용하세요.
2. "이렇게 하면 성공합니다", "확실히 잘 될 것입니다" 같은 단정적인 표현은
   절대 쓰지 마세요. "~해보는 것도 고려해볼 만합니다", "~전략이 하나의
   방법이 될 수 있습니다"처럼 제안하는 톤으로 쓰고, 확정적인 조언이 아니라
   참고용 아이디어라는 걸 문장에서 자연스럽게 드러내세요.
3. 일반적인 창업·마케팅 지식을 활용해 구체적으로 제안하세요. 예를 들어
   경쟁강도가 낮게 나왔으면(경쟁이 치열하면) 틈새 메뉴나 비혼잡 시간대
   공략을, 배후수요가 낮으면 특정 타겟 고객층 공략이나 배달·포장 비중
   확대를 제안하는 식입니다. "열심히 하세요", "좋은 서비스를 제공하세요"
   같은 막연한 조언은 쓰지 마세요.
4. 이모지 없이, 2~4문장 정도의 짧은 한국어 문단 하나로 작성하세요.
5. 출력은 바로 사용자에게 보여줄 텍스트만 작성하세요. 마크다운 문법(##, **,
   - 등)이나 따옴표로 감싸지 마세요."""


def _build_payload(candidate: AnalyzeResponse) -> dict:
    md = candidate.market_data
    return {
        "행정동명": md.region.행정동명,
        "업종": candidate.category,
        "total_score": candidate.score.total_score,
        "breakdown": candidate.score.breakdown.model_dump(),
        "동일업종_경쟁업체수": md.competitors.total_count,
        "폐업률(%)": md.closure_stats.폐업률 if md.closure_stats.data_available else None,
    }


def _call_gemini(payload: dict) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되어 있지 않음")

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=_TIMEOUT_MS))

    contents = (
        f"지역 분석 데이터(JSON):\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "위 데이터를 바탕으로 차별화 전략을 제안해 주세요."
    )

    response = client.models.generate_content(
        model=_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            temperature=0.5,  # 비교 리포트(0.4)보다 살짝 높게 — 여긴 창의적 제안이 목적
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    if not response.text:
        raise RuntimeError("Gemini 응답이 비어 있음")
    return response.text


def generate_differentiation_strategy(candidate: AnalyzeResponse) -> str | None:
    """실패하면 예외를 삼키고 None을 반환한다 — report.py의 점수 기반 폴백과
    달리, 창작 조언은 억지로 대체 문구를 만들 근거가 없어 그냥 비워둔다."""
    try:
        return _call_gemini(_build_payload(candidate))
    except Exception as e:  # noqa: BLE001 — 실패는 항상 None으로 흡수
        logger.warning("차별화 전략 생성 실패: %s", e)
        return None
