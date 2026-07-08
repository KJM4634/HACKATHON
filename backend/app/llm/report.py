"""
PRD 3.4: 스코어링 엔진 출력(점수+세부지표+data_limitations)을 LLM에 넘겨
Top3 추천 입지 + 선정 이유 + 리스크 요인을 자연어로 받는다.

LLM은 숫자를 재계산하지 않고 해설만 한다 — 점수 로직과 리포트 문장이 항상
일치하도록 프롬프트에서 명시적으로 금지한다. Gemini API 호출이 실패하거나
느리면(타임아웃) 점수만으로 만든 기본 템플릿 리포트로 대체한다(PRD 8장).

Claude API 대신 Gemini(무료 티어)를 쓰기로 함에 따라 SDK 호출부만 google-genai로
교체했고, 프롬프트 구조(무엇을 왜 지시하는지)는 그대로다.
"""

import json
import logging
import os

from google import genai
from google.genai import types

from app.schemas import AnalyzeResponse

logger = logging.getLogger(__name__)

# gemini-2.5-flash 무료 티어는 실측 결과 일일 20회로 매우 낮음(2026-07-08,
# 429 응답의 quotaValue로 직접 확인). gemini-2.5-flash-lite로 교체 —
# 모델별로 쿼터가 완전히 분리돼 있고(quotaId가 PerModel), 공개된 자료 기준으로도
# flash보다 일일 한도가 훨씬 높다. 품질이 필요한 서술형 리포트보다 원래
# 가벼운 모델을 염두에 두고 설계된 프롬프트라 품질 저하 리스크도 작다.
_MODEL = "gemini-2.5-flash-lite"
_TIMEOUT_MS = 15_000
_MAX_OUTPUT_TOKENS = 4096

_SYSTEM_INSTRUCTION = """당신은 부울경(부산/울산/경남) 지역 상권 분석 리포트를 쓰는 어시스턴트입니다.
독자는 창업을 고민하는 예비 소상공인입니다.

아래 사용자 메시지에 여러 후보 지역의 점수와 세부 지표가 JSON으로 주어집니다.
당신의 역할은 이 숫자를 "해설"하는 것뿐입니다. 다음 규칙을 반드시 지키세요:

1. 절대로 점수를 다시 계산하거나 고치지 마세요. 주어진 총점(total_score)과
   세부점수(breakdown)를 그대로 인용만 하세요. 당신이 직접 점수를 산출한 것처럼
   말하지 마세요.
2. 주어진 후보 중 total_score가 높은 순으로 Top 3(후보가 3개 미만이면 있는
   만큼 전부)를 추천하고, 각각 선정 이유를 배후수요/경쟁강도/수익성 등
   구체적인 지표와 원자료 숫자(방문인구, 경쟁업체수 등)를 근거로 설명하세요.
3. 각 지역의 리스크 요인을 언급하세요(예: 경쟁 밀집도가 높음, 최근 폐업률이 높음).
4. 세부점수(특히 수익성)가 0에 가깝게 낮게 나온 지역이 있어도 "이 업종은
   완전히 실패한다", "장사가 안 된다" 같은 단정적이고 부정적인 표현은 쓰지
   마세요. 대신 "매출 규모가 상대적으로 작은 상권으로 보입니다" 처럼 완곡하게
   표현하세요.
5. 각 후보의 data_limitations 필드에는 이 점수가 어떤 데이터 한계를 안고
   있는지(예: 구 단위 인구 추정치, 접근성 데이터 없어 가중치 재분배 등)가
   적혀있습니다. 이걸 기술적으로 나열하지 말고, 리포트 말미에 "참고사항"
   섹션에서 예비 창업자가 이해할 수 있는 말로 1~2문장으로 자연스럽게
   풀어서 설명하세요. 여러 후보가 같은 한계를 공유하면 한 번만 언급하세요.
6. 전문 용어를 최소화하고, 친절하지만 담백한 톤으로 쓰세요. 과장된 확신이나
   이모지는 쓰지 마세요.
7. 출력은 바로 사용자에게 보여줄 한국어 리포트 텍스트만 작성하세요. JSON이나
   마크다운 코드블록으로 감싸지 마세요.
8. 마크다운 문법을 쓰지 마세요(##, **, -, --- 등). 화면에는 이 문자들이 그대로
   글자로 보이므로, 제목이나 강조 없이 자연스러운 문단과 줄바꿈만으로 구성하세요."""


def _build_candidate_payload(candidates: list[AnalyzeResponse]) -> list[dict]:
    """점수+세부지표+data_limitations만 남긴 가벼운 JSON. 원자료 전체를 넘기지
    않는 이유: 프롬프트를 짧게 유지하고, LLM이 원자료로 자기 점수를 만들어내려는
    유혹을 줄이기 위함(위 규칙 1)."""
    payload = []
    for c in candidates:
        md = c.market_data
        total_visits = sum(h.평균방문인구수 for h in md.foot_traffic)
        payload.append(
            {
                "행정동명": md.region.행정동명,
                "total_score": c.score.total_score,
                "breakdown": c.score.breakdown.model_dump(),
                "weights_used": c.score.weights_used.model_dump(),
                "참고_원자료": {
                    "일_총_방문인구": total_visits,
                    "구_총인구수": md.population.총인구수,
                    "동일업종_경쟁업체수": md.competitors.total_count,
                    "폐업률(%)": md.closure_stats.폐업률 if md.closure_stats.data_available else None,
                },
                "data_limitations": c.score.data_limitations,
            }
        )
    return payload


def _call_gemini(category: str, payload: list[dict]) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되어 있지 않음")

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=_TIMEOUT_MS))

    contents = (
        f"업종: {category}\n\n"
        f"후보 지역 분석 데이터(JSON):\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "위 데이터를 바탕으로 리포트를 작성해 주세요."
    )

    response = client.models.generate_content(
        model=_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            temperature=0.4,
            # 이 리포트는 점수 재해석/요약일 뿐 복잡한 추론이 필요 없는데, thinking이
            # 켜져 있으면 사고 토큰이 max_output_tokens를 먼저 소비해 본문이 잘렸다
            # (실측: thoughts_token_count=934로 답변 본문이 중간에 끊김).
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    if not response.text:
        raise RuntimeError("Gemini 응답이 비어 있음")
    return response.text


def _fallback_report(category: str, candidates: list[AnalyzeResponse]) -> str:
    """LLM 없이 점수만으로 만드는 기본 템플릿 (PRD 8장: LLM 실패 시 대응)."""
    ranked = sorted(candidates, key=lambda c: c.score.total_score, reverse=True)
    lines = [f"[{category}] 후보 {len(ranked)}곳 점수 요약 (AI 리포트 생성 실패로 기본 요약을 표시합니다)", ""]
    for i, c in enumerate(ranked, start=1):
        b = c.score.breakdown
        lines.append(
            f"{i}. {c.region.행정동명} — 총점 {c.score.total_score}점 "
            f"(배후수요 {b.배후수요} / 경쟁강도 {b.경쟁강도} / 수익성 {b.수익성})"
        )
    return "\n".join(lines)


def generate_report(category: str, candidates: list[AnalyzeResponse]) -> tuple[str, bool]:
    """(리포트 텍스트, is_fallback) 반환. LLM 실패 시 예외를 삼키고 폴백 리포트로 대체."""
    payload = _build_candidate_payload(candidates)
    try:
        return _call_gemini(category, payload), False
    except Exception as e:  # noqa: BLE001 — LLM 실패는 항상 폴백으로 흡수
        logger.warning("Gemini 리포트 생성 실패, 폴백 템플릿 사용: %s", e)
        return _fallback_report(category, candidates), True
