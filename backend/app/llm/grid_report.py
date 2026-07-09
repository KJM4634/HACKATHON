"""
격자 셀 하나의 점수를 자연어로 해설한다. report.py(행정동 여러 곳 Top3 비교)와
가장 다른 점: 이 점수는 부산 전체 기준이 아니라 "같은 행정동 안 격자들끼리의
상대 비교"라서, 프롬프트에서 이 맥락을 반드시 짚어주지 않으면 Gemini가 절대
점수처럼 착각한 문장을 쓸 위험이 있다 — _SYSTEM_INSTRUCTION 맨 앞에 명시해둔
이유다.

셀 클릭마다 자동으로 호출하지 않는다("AI 해설 보기" 버튼을 눌렀을 때만) — 격자가
행정동 하나에 최대 100개 안팎이라, 자동 호출이면 Gemini 무료 티어 일일 한도를
금방 다 쓴다. 호출부(app/api/grid.py)가 (region_id, category, cell_id) 키로
캐싱해서 같은 셀을 다시 눌러도 재호출하지 않는다.
"""

import json
import logging
import os

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.1-flash-lite"
_TIMEOUT_MS = 15_000
_MAX_OUTPUT_TOKENS = 2048

_SYSTEM_INSTRUCTION = """당신은 부산 상권 분석 리포트를 쓰는 어시스턴트입니다.
독자는 창업을 고민하는 예비 소상공인입니다.

아래 사용자 메시지에 "격자" 하나(행정동을 100~1000m 사각형으로 잘게 나눈 것 중
하나)의 점수와 세부 지표가 JSON으로 주어집니다. 다음 규칙을 반드시 지키세요:

1. 가장 중요한 규칙: 이 점수는 부산 전체를 기준으로 한 절대 점수가 아니라,
   "같은 행정동 안 다른 격자들과 비교했을 때"의 상대 점수입니다. 리포트 첫
   문장 또는 두 번째 문장 안에 이 사실을 반드시 자연스럽게 언급하세요(예:
   "이 격자는 [행정동명] 안에서 비교했을 때…" 같은 식). 부산 전체에서 몇 등인지,
   다른 동과 비교해서 어떤지처럼 이 데이터에 없는 비교를 지어내지 마세요.
2. 절대로 점수를 다시 계산하거나 고치지 마세요. 주어진 총점(total_score)과
   세부점수(breakdown)를 그대로 인용만 하세요.
3. 이 격자의 강점과 약점을 배후수요/경쟁강도/수익성 세부점수와 원자료 숫자
   (경쟁업체수, 폐업률 등)를 근거로 설명하세요.
4. 세부점수가 0에 가깝게 낮아도 "완전히 실패한다", "장사가 안 된다" 같은
   단정적이고 부정적인 표현은 쓰지 마세요. "이 행정동 안에서는 상대적으로
   약한 편"처럼 완곡하게 표현하세요.
5. "폐업률_표본부족"이 true인 경우, 폐업률 수치 자체를 언급하지 말고 "표본이
   적어 폐업률 대신 밀집도만 반영했다"는 사실만 짧게 언급하세요.
6. "대안_격자" 필드가 있다면, 이 격자보다 점수가 더 높은 같은 행정동 내 다른
   구역이 있다는 뜻입니다. 이름이나 좌표로 그 구역을 지칭하지 말고(주어진
   데이터에 그런 이름이 없습니다), distance_km와 total_score만 근거로 "바로
   인근(약 [거리]km)에 점수가 더 높은 구역이 있다"는 정도로 한두 문장만
   짧게 언급하세요. 목록이 없거나 비어 있으면 이 언급을 생략하세요.
7. 전문 용어를 최소화하고, 친절하지만 담백한 톤으로 쓰세요. 과장된 확신이나
   이모지는 쓰지 마세요.
8. 전체 3~5문장, 짧은 문단 하나 또는 둘로 작성하세요(행정동 전체를 다루는
   리포트보다 훨씬 짧아야 합니다 — 격자 하나짜리 설명이라서입니다).
9. 출력은 바로 사용자에게 보여줄 한국어 텍스트만 작성하세요. JSON이나
   마크다운 문법(##, **, -, --- 등)으로 감싸지 마세요."""


def _build_cell_payload(
    label: str,
    total_score: int,
    breakdown: dict,
    competitor_count: int,
    closure_available: bool,
    closure_rate: float,
    closure_sample: int,
    alternatives: list[dict],
) -> dict:
    payload = {
        "격자_라벨": label,
        "total_score": total_score,
        "breakdown": breakdown,
        "경쟁업체수": competitor_count,
    }
    if closure_available:
        payload["폐업률(%)"] = closure_rate
    else:
        payload["폐업률_표본부족"] = True
        payload["폐업_표본_건수"] = closure_sample
    if alternatives:
        payload["대안_격자"] = alternatives
    return payload


def _call_gemini(category: str, payload: dict) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되어 있지 않음")

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=_TIMEOUT_MS))

    contents = (
        f"업종: {category}\n\n"
        f"격자 분석 데이터(JSON):\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "위 데이터를 바탕으로 이 격자에 대한 짧은 해설을 작성해 주세요."
    )

    response = client.models.generate_content(
        model=_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            temperature=0.4,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    if not response.text:
        raise RuntimeError("Gemini 응답이 비어 있음")
    return response.text


def _fallback_report(
    label: str,
    total_score: int,
    breakdown: dict,
    competitor_count: int,
    closure_available: bool,
    closure_rate: float,
    alternatives: list[dict],
) -> str:
    """LLM 없이 숫자만으로 만드는 기본 템플릿 (PRD 8장과 같은 방식)."""
    lines = [
        f"{label}은 같은 행정동 안에서 비교했을 때 총점 {total_score}점입니다.",
        f"배후수요 {breakdown['배후수요']} / 경쟁강도 {breakdown['경쟁강도']} / 수익성 {breakdown['수익성']} (세부점수).",
        f"동일업종 경쟁업체는 {competitor_count}개입니다.",
    ]
    if closure_available:
        lines.append(f"최근 1년 폐업률은 {closure_rate}%입니다.")
    else:
        lines.append("이 격자는 폐업률 표본이 부족해 경쟁업체 밀집도만 반영했습니다.")
    if alternatives:
        best = alternatives[0]
        lines.append(
            f"같은 행정동 내 약 {best['distance_km']}km 거리의 구역이 총점 {best['total_score']}점으로 더 높게 나타났습니다."
        )
    return " ".join(lines)


def generate_grid_cell_report(
    category: str,
    label: str,
    total_score: int,
    breakdown: dict,
    competitor_count: int,
    closure_available: bool,
    closure_rate: float,
    closure_sample: int,
    alternatives: list[dict],
) -> tuple[str, bool]:
    """(리포트 텍스트, is_fallback) 반환. LLM 실패 시 예외를 삼키고 폴백으로 대체."""
    payload = _build_cell_payload(
        label, total_score, breakdown, competitor_count, closure_available, closure_rate, closure_sample, alternatives
    )
    try:
        return _call_gemini(category, payload), False
    except Exception as e:  # noqa: BLE001 — LLM 실패는 항상 폴백으로 흡수
        logger.warning("격자 셀 Gemini 리포트 생성 실패, 폴백 템플릿 사용: %s", e)
        return (
            _fallback_report(label, total_score, breakdown, competitor_count, closure_available, closure_rate, alternatives),
            True,
        )
