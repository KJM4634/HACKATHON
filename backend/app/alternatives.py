"""
선택한 지역의 점수가 낮으면, 같은 업종 기준으로 더 높은 점수를 가지면서 가까운
(3km 이내) 대안 지역을 거리순 최대 3곳 찾는다.

"낮다"의 기준은 퍼센타일이 아니라 고정 점수(50점 이하)로 잡았다 — 퍼센타일로
하려면 "낮은지 판단"하는 데도 매번 206개 행정동 점수를 전부 다시 계산해야 해서,
대부분의(이미 점수가 괜찮은) 요청에도 불필요한 비용이 붙는다. 고정 기준이면
후보 자신의 점수만 보고 즉시 판단할 수 있고, 실제로 낮을 때만(그때는 어차피
대안을 찾으려고 전체를 훑어야 하니) 비용을 쓴다.
"""

import math

from app.schemas import AlternativeRegion, RegionInfo, ScoreResult

LOW_SCORE_THRESHOLD = 50  # 이 점수 "이하"면 대안 추천 대상 (PRD 요청의 "50점 미만"을
# 포함해 서면·카페(정확히 50점)처럼 경계값도 대안 추천이 걸리도록 이하로 잡음)
MAX_DISTANCE_KM = 3.0
MAX_ALTERNATIVES = 3


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표 간 대권거리(km). 도시 규모 거리에서 오차가 미미해 흔히 쓰는 근사식."""
    radius_km = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def find_alternatives(
    target: RegionInfo,
    own_score: int,
    all_scores: dict[str, ScoreResult],
    region_by_id: dict[str, RegionInfo],
) -> list[AlternativeRegion]:
    """own_score가 LOW_SCORE_THRESHOLD 이하일 때 호출한다고 가정 — 호출 여부 판단은
    호출부(analyze.py) 책임이고, 여기는 순수하게 "더 낫고 가까운 곳 찾기"만 한다.

    세부점수(breakdown)까지 같이 담아두는 이유: LLM이 "구체적으로 왜 더 나은지"를
    말하려면 총점 하나만으론 근거가 없어 지어낼 수밖에 없다. 배후수요/경쟁강도/
    수익성처럼 실제로 더 나은 지표를 짚어 말할 수 있게 원자료를 그대로 준다."""
    candidates = []
    for region_id, result in all_scores.items():
        if region_id == target.region_id or result.total_score <= own_score:
            continue
        other = region_by_id[region_id]
        distance_km = haversine_km(target.위도, target.경도, other.위도, other.경도)
        if distance_km <= MAX_DISTANCE_KM:
            candidates.append(
                AlternativeRegion(
                    region=other,
                    score=result.total_score,
                    distance_km=round(distance_km, 2),
                    breakdown=result.breakdown,
                )
            )

    candidates.sort(key=lambda c: c.distance_km)
    return candidates[:MAX_ALTERNATIVES]
