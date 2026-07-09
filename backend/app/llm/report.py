# backend/app/llm/report.py
import json
import logging
import os
from google import genai
from google.genai import types

from app.schemas import AnalyzeResponse
from app.llm.review_analyzer import generate_review_summary

logger = logging.getLogger(__name__)

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
9. (긴급 예외 처리) 만약 제공된 데이터에서 '폐업률'이나 '동일업종_경쟁업체수'가 null 
    이거나 0으로 표기되어 있다면, 상권이 나쁜 것이 아니라 "공공데이터 수집 누락"입니다.
    이 경우 점수가 낮더라도 절대 무조건 부정적으로 평가하지 마세요. 대신 당신이 사전에 
    학습한 해당 지역(행정동명)의 실제 번화가 정도, 지리적 특성, 유동인구 지식을 바탕으로 
    AI의 자체적인 판단을 더해 상권의 잠재력을 평가하고 적극적으로 대안을 추천해 주세요."""


def _build_candidate_payload(candidates: list[AnalyzeResponse]) -> list[dict]:
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
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    if not response.text:
        raise RuntimeError("Gemini 응답이 비어 있음")
    return response.text


def _fallback_report(category: str, candidates: list[AnalyzeResponse]) -> str:
    ranked = sorted(candidates, key=lambda c: c.score.total_score, reverse=True)
    lines = [f"[{category}] 후보 {len(ranked)}곳 점수 요약 (AI 리포트 생성 실패로 기본 요약을 표시합니다)", ""]
    for i, c in enumerate(ranked, start=1):
        b = c.score.breakdown
        lines.append(
            f"{i}. {c.region.행정동명} — 총점 {c.score.total_score}점 "
            f"(배후수요 {b.배후수요} /경쟁강도 {b.경쟁강도} / 수익성 {b.수익성})"
        )
        if c.alternatives:
            alt_text = ", ".join(f"{a.region.행정동명}({a.score}점, {a.distance_km}km)" for a in c.alternatives)
            lines.append(f"   ⚠ 이 지역은 점수가 낮습니다. 인근 대안: {alt_text}")
    return "\n".join(lines)


def generate_report(category: str, candidates: list[AnalyzeResponse]) -> tuple[str, bool]:
    """(리포트 텍스트, is_fallback) 반환. LLM 실패 시 예외를 삼키고 폴백 리포트로 대체."""
    payload = _build_candidate_payload(candidates)
    try:
        main_report_text = _call_gemini(category, payload)
        
        # 클릭한 메인 지역에 대해서만 네이버 블로그 리뷰 분석 추가
        if candidates and len(candidates) > 0:
            target_region_name = candidates[0].region.행정동명
            review_summary = generate_review_summary(target_region_name, category)
            if review_summary:
                main_report_text += f"\n\n{review_summary}"

        return main_report_text, False
    except Exception as e:
        logger.warning("Gemini 리포트 생성 실패, 폴백 템플릿 사용: %s", e)
        return _fallback_report(category, candidates), True