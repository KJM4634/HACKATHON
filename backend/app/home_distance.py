"""
사용자가 지도에서 지정한 "우리 집" 위치와 후보 지역 사이의 참고용 거리 배지.
budget.py/trend.py와 같은 패턴 — total_score 계산에는 전혀 반영되지 않는다.

이동 "시간"은 일부러 넣지 않았다(HomeDistance 스키마 docstring 참고) — 실시간
경로/교통 API가 없어서 직선거리를 어떤 평균 속도로 나누든, 실제 도로 경로·신호·
정체를 전혀 반영 못 하는 값을 "차로 O분"처럼 확정적인 숫자로 보여주는 건 신뢰도
낮은 값을 사실처럼 오해시킬 리스크가 있다고 판단했다. 대신 haversine 직선거리
(km)만 보여주고, 이 한계를 화면(배지 문구 + 데이터 안내 푸터)에도 명시한다.
"""

from app.alternatives import haversine_km
from app.schemas import HomeDistance


def estimate_home_distance(home_lat: float, home_lng: float, target_lat: float, target_lng: float) -> HomeDistance:
    return HomeDistance(distance_km=round(haversine_km(home_lat, home_lng, target_lat, target_lng), 1))
