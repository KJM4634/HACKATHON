"""
PRD 3.4: 스코어링 엔진 출력(점수+세부지표)을 LLM에 넘겨 Top3 추천 입지 + 선정
이유 + 리스크 요인을 자연어로 받는다.

data_limitations(구 단위 인구 추정, 접근성 데이터 없음 등)는 리포트마다 거의
똑같은 문구가 반복돼 개별 리포트를 읽는 재미/신뢰도를 떨어뜨렸다 — 이제 이
정보는 Gemini에게 주지 않고, 프론트 페이지 하단의 고정 "데이터 안내" 섹션에서
한 번만 보여준다(App.jsx). API 응답의 ScoreResult.data_limitations 필드
자체는 그대로 남겨둔다 — 어떤 근거로 가중치가 재분배됐는지는 내부적으로/개발
문서 용도로 계속 필요하다.

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

# gemini-2.5-flash와 gemini-2.5-flash-lite 둘 다 무료 티어 RPD가 20으로 동일함을
# AI Studio 콘솔에서 직접 확인(2026-07-08) — "flash-lite가 더 높다"던 서드파티
# 자료는 이 계정 기준으로는 틀렸다. gemini-3.1-flash-lite로 교체 — RPD 500(RPM
# 15)으로 훨씬 여유롭고, Google이 gemini-2.5-flash-lite의 공식 후속(migration
# target)으로 지정한 모델이라 임의 선택이 아니다. gemini-2.5-flash/flash-lite는
# 2026-10-16 지원 종료 예정인 반면, gemini-3.1-flash-lite는 2027-05-07까지라
# 여유가 더 있다(다만 이것도 영구적이진 않으니, 그 시점 전에 한 번 더 확인 필요).
_MODEL = "gemini-3.1-flash-lite"
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
5. 전문 용어를 최소화하고, 친절하지만 담백한 톤으로 쓰세요. 과장된 확신이나
   이모지는 쓰지 마세요.
6. 출력은 바로 사용자에게 보여줄 한국어 리포트 텍스트만 작성하세요. JSON이나
   마크다운 코드블록으로 감싸지 마세요. "참고사항", "데이터 한계" 같은
   섹션은 만들지 마세요 — 그 내용은 이 서비스의 다른 화면에서 이미 한 번만
   보여주고 있으니, 여기서는 이 지역만의 분석 내용에 집중하세요.
7. 마크다운 문법을 쓰지 마세요(##, **, -, --- 등). 화면에는 이 문자들이 그대로
   글자로 보이므로, 제목이나 강조 없이 자연스러운 문단과 줄바꿈만으로 구성하세요.
8. 어떤 후보에 "대안_지역" 필드가 있다면(점수가 낮아 시스템이 미리 찾아둔,
   더 점수가 높고 가까운 지역들입니다), 그 후보를 설명한 직후에 비교 문단을
   추가하세요. "대안_지역"이 없거나 빈 후보는 이 비교 없이 평소대로 설명하고,
   아래는 건너뛰세요. 이 문단은 반드시 다음 순서로, 정확히 이 형태를 따라
   쓰세요(괄호 안만 실제 내용으로 채우세요):

   1) 첫 문장은 결론부터: "이런 이유로 [원래 후보 행정동명] 인근(3km 이내)
      에서는 [대안_지역 중 total_score가 가장 높은 곳의 행정동명]을
      추천드립니다." "인근(3km 이내)"라는 표현을 꼭 넣어서, 아무 지역이나
      비교한 게 아니라 가까운 곳들 중에서 골랐다는 게 드러나게 하세요.
      세부점수를 죽 나열하다가 맨 마지막에 결론을 붙이는 순서(예: "…아쉽습니다.
      그래서 추천드립니다")는 안 됩니다 — 결론 문장이 이 문단의 첫 문장이어야
      합니다.
   2) 그다음, "대안_지역" 각각에 대해 한 문장씩: "[대안 행정동명](distance_km
      로 도보/차로 거리 언급, 예: 약 0.5km 거리)에서 창업하시면 [그 지역
      breakdown이 원래 후보 breakdown보다 실제로 더 높은 지표 하나를 골라,
      그 지표가 뜻하는 구체적 강점 — 예: 배후수요가 더 높음 = 유동인구가 더
      많음, 경쟁강도가 더 높음 = 경쟁이 덜 치열함, 수익성이 더 높음 = 매출
      규모가 더 큼] 덕분에 더 잘될 가능성이 높습니다." 한 지역에 breakdown상
      더 나은 지표가 여러 개면 그중 차이가 가장 큰 것 하나만 고르세요. 두
      지역의 수치를 비교하는 복잡한 문장(예: "…와 달리 …이면서도…") 대신,
      대안 지역 하나당 이 단순한 문장 하나로 끝내세요.
   3) 전체 톤은 원래 지역을 비판하거나 "글렀다"는 식으로 단정하지 말고,
      "그래도 이렇게 더 나은 대안이 있다"는 건설적인 톤을 유지하세요(규칙
      4의 완곡한 표현도 함께 지키세요).
   4) breakdown/total_score/distance_km에 없는 내용(임대료, 실제 유동인구
      특성 등)은 추측해서 말하지 마세요 — 반드시 주어진 숫자 안에서만 근거를
      대세요.
9. 후보 JSON에 "예산_참고" 필드가 있다면(사용자가 예상 월세 예산을 입력한
   경우), 그 후보를 설명하는 문단 중간에 자연스럽게 한 문장만 추가하세요.
   "예산_참고.판단"에 있는 문구의 취지를 그대로 살리되 단정하지 말고, 예산
   금액(만원 단위로 반올림해서 언급)과 함께 완곡하게 쓰세요 — 예: "말씀하신
   예산 200만원 기준으로는, 이 지역 상권 규모에 비해 다소 부담될 수
   있습니다." 이건 실제 임대료를 계산한 게 아니라 상권 규모 대비 대략적인
   참고일 뿐이라는 뉘앙스를 유지하세요. "예산_참고" 필드가 없는 후보는 이
   문장을 아예 쓰지 마세요.
10. 후보 JSON에 "최근_추세_참고" 필드가 있다면, 그 후보를 설명하는 문단
    어딘가에 자연스럽게 한 문장만 추가하세요. "최근_추세_참고.판단"의 취지를
    그대로 살리되 단정하지 말고 "~로 보입니다", "~인 편입니다" 같은 완곡한
    표현을 쓰세요 — 예: "최근 1년 사이 매출 흐름은 부산 평균보다 빠르게
    성장하는 추세로 보입니다." 이건 예측이 아니라 지난 1년간의 흐름을
    참고로 짚어주는 것일 뿐이니 "앞으로도 계속 성장할 것"처럼 미래를
    단정하지 마세요. "최근_추세_참고" 필드가 없는 후보는 이 문장을 아예
    쓰지 마세요."""


def _build_candidate_payload(candidates: list[AnalyzeResponse]) -> list[dict]:
    """점수+세부지표만 남긴 가벼운 JSON. 원자료 전체를 넘기지 않는 이유:
    프롬프트를 짧게 유지하고, LLM이 원자료로 자기 점수를 만들어내려는 유혹을
    줄이기 위함(위 규칙 1). data_limitations는 일부러 안 넣는다 — 리포트마다
    거의 같은 문구가 반복돼서 개별 리포트에 안 어울렸고, 그 정보는 이제
    페이지 하단 고정 안내에서 한 번만 보여준다."""
    payload = []
    for c in candidates:
        md = c.market_data
        total_visits = sum(h.평균방문인구수 for h in md.foot_traffic)
        entry = {
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
        }
        if c.alternatives:
            entry["대안_지역"] = [
                {
                    "행정동명": a.region.행정동명,
                    "total_score": a.score,
                    "distance_km": a.distance_km,
                    "breakdown": a.breakdown.model_dump(),
                }
                for a in c.alternatives
            ]
        # is_unreliable(입력값이 30만~1,000만원 범위 밖)이면 Gemini에게 아예 안 넘긴다 —
        # "여유/부담" 판단 자체를 유보한 상태라 리포트에서 언급할 내용이 없다.
        if c.budget_fit and not c.budget_fit.is_unreliable:
            entry["예산_참고"] = {
                "월세_예산_만원": round(c.budget_fit.monthly_budget_krw / 10_000),
                "판단": c.budget_fit.label,
            }
        # data_available=False(이력 부족 행정동)면 Gemini에게 안 넘긴다 — 언급할
        # 추세 자체가 없는 상태라, 억지로 "데이터가 없다"는 문장을 만들게 하지 않는다.
        if c.trend and c.trend.data_available:
            entry["최근_추세_참고"] = {
                "이_동네_YoY_증감률(%)": c.trend.dong_yoy_pct,
                "부산_전체_중앙값_YoY_증감률(%)": c.trend.city_median_yoy_pct,
                "판단": c.trend.label,
            }
        payload.append(entry)
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
    """LLM 없이 점수만으로 만드는 기본 템플릿 (PRD 8장: LLM 실패 시 대응).

    대안 비교는 Gemini의 해설 없이도 핵심 정보(어디가, 몇 점 차이로, 얼마나
    가까운지)는 전달되게 한 줄만 덧붙인다."""
    ranked = sorted(candidates, key=lambda c: c.score.total_score, reverse=True)
    lines = [f"[{category}] 후보 {len(ranked)}곳 점수 요약 (AI 리포트 생성 실패로 기본 요약을 표시합니다)", ""]
    for i, c in enumerate(ranked, start=1):
        b = c.score.breakdown
        lines.append(
            f"{i}. {c.region.행정동명} — 총점 {c.score.total_score}점 "
            f"(배후수요 {b.배후수요} / 경쟁강도 {b.경쟁강도} / 수익성 {b.수익성})"
        )
        if c.alternatives:
            alt_text = ", ".join(f"{a.region.행정동명}({a.score}점, {a.distance_km}km)" for a in c.alternatives)
            lines.append(f"   ⚠ 이 지역은 점수가 낮습니다. 인근 대안: {alt_text}")
    return "\n".join(lines)


def generate_report(category: str, candidates: list[AnalyzeResponse]) -> tuple[str, bool]:
    """(리포트 텍스트, is_fallback) 반환. LLM 실패 시 예외를 삼키고 폴백 리포트로 대체."""
    payload = _build_candidate_payload(candidates)
    try:
        return _call_gemini(category, payload), False
    except Exception as e:  # noqa: BLE001 — LLM 실패는 항상 폴백으로 흡수
        logger.warning("Gemini 리포트 생성 실패, 폴백 템플릿 사용: %s", e)
        return _fallback_report(category, candidates), True
