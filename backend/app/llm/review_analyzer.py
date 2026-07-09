# backend/app/llm/review_analyzer.py
import urllib.request
import urllib.parse
import json
import os
import re
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# report.py/llm/grid_report.py와 같은 모델·컨벤션을 맞춘다. thinking_budget=0이
# 없으면 사고 토큰이 max_output_tokens를 먼저 소비해 본문이 잘리는 버그를 이미
# 겪었다(report.py 주석 참고) — 재발 방지 차원에서 반드시 넣어야 한다. timeout도
# 마찬가지로 없으면 Gemini가 느릴 때 무한정 대기하게 된다.
_MODEL = "gemini-3.1-flash-lite"
_TIMEOUT_MS = 15_000
_MAX_OUTPUT_TOKENS = 1024

def _fetch_naver_blog_reviews(query: str, display: int = 15) -> str:
    client_id = (os.environ.get("NAVER_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("NAVER_CLIENT_SECRET") or "").strip()

    if not client_id or not client_secret:
        logger.warning("네이버 API 키가 없습니다. 리뷰 분석을 건너뜁니다.")
        return ""

    encText = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/blog?query={encText}&display={display}"
    
    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", client_id)
    request.add_header("X-Naver-Client-Secret", client_secret)
    
    try:
        response = urllib.request.urlopen(request)
        rescode = response.getcode()
        if rescode == 200:
            response_body = response.read()
            data = json.loads(response_body.decode('utf-8'))
            
            # 검색된 블로그의 요약(description) 내용만 추출
            snippets = [item['description'] for item in data.get('items', [])]
            
            # 네이버 API가 주는 <b>, </b> 같은 HTML 태그 깔끔하게 제거
            clean_snippets = [re.sub(r'<[^>]+>', '', s) for s in snippets]
            
            # 하나의 긴 텍스트로 합치기
            return " ".join(clean_snippets)
        else:
            logger.error(f"네이버 API 에러: {rescode}")
            return ""
    except Exception as e:
        logger.error(f"블로그 데이터 수집 실패: {e}")
        return ""


def generate_review_summary(region_name: str, category: str) -> str:
    """수집된 리뷰를 바탕으로 제미나이가 장/단점을 요약해주는 함수"""
    # 1. 검색어 만들기 (예: "해운대구 좌4동 카페 후기")
    query = f"{region_name} {category} 후기"
    review_text = _fetch_naver_blog_reviews(query)
    
    if not review_text.strip():
        return "" # 데이터가 없으면 빈 문자열 반환

    # 2. 제미나이 호출 준비
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return ""

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=_TIMEOUT_MS))

    prompt = f"""
    당신은 데이터 기반 창업 컨설턴트입니다. 
    아래는 '{region_name}' 지역의 '{category}' 방문객들이 작성한 네이버 블로그 리뷰 텍스트 모음입니다.
    이 텍스트의 감성과 키워드를 분석하여, 예비 창업자가 반드시 알아야 할 '현재 상권의 기회(장점)' 2가지와 '불만/위협요소(단점)' 2가지를 추출해주세요.
    
    [블로그 리뷰 원본 데이터]
    {review_text}
    
    [출력 규칙]
    - 반드시 아래 포맷을 지켜서 작성하세요. 마크다운(## 등)은 쓰지 마세요.
    - 장점과 단점은 각각 명확한 한 줄 키워드와 짧은 설명으로 구성하세요.
    - 블로그 원문에 없는 내용을 상상해서 쓰지 마세요.

    출력 포맷:
    
    📌 [방문자 생생 리뷰 분석 (AI 요약)]
    🟢 상권의 기회 (고객들이 좋아하는 포인트)
    1. (여기에 작성)
    2. (여기에 작성)
    
    🔴 상권의 위협 (고객들의 숨은 불만/니즈)
    1. (여기에 작성)
    2. (여기에 작성)
    
    💡 요기차려 전략 제안: (위 내용을 바탕으로 창업자에게 한 줄 조언)
    """
    
    try:
        response = client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=_MAX_OUTPUT_TOKENS,
                temperature=0.4,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        return response.text if response.text else ""
    except Exception as e:
        logger.warning(f"리뷰 요약 제미나이 호출 실패: {e}")
        return ""