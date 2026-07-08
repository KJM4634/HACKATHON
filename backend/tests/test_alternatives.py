from app.alternatives import MAX_ALTERNATIVES, MAX_DISTANCE_KM, find_alternatives, haversine_km
from app.schemas import RegionInfo, ScoreBreakdown, ScoreResult, ScoreWeights


def _region(region_id, name, lat, lon):
    return RegionInfo(
        region_id=region_id,
        행정동코드=region_id,
        행정동명=name,
        시도명="부산광역시",
        시군구명="테스트구",
        위도=lat,
        경도=lon,
    )


def _score_result(total_score, 배후수요=50, 경쟁강도=50, 수익성=50):
    return ScoreResult(
        total_score=total_score,
        breakdown=ScoreBreakdown(배후수요=배후수요, 경쟁강도=경쟁강도, 접근성=None, 수익성=수익성),
        weights_used=ScoreWeights(배후수요=0.4375, 경쟁강도=0.375, 접근성=0.0, 수익성=0.1875),
        data_limitations=[],
        is_placeholder=False,
    )


def test_haversine_km_zero_for_same_point():
    assert haversine_km(35.15, 129.05, 35.15, 129.05) == 0.0


def test_haversine_km_matches_known_distance_roughly():
    # 서면(부전2동)과 해운대(우1동) 대략 좌표 — 실제로 8~10km 안팎이어야 함
    d = haversine_km(35.1554, 129.0586, 35.1632, 129.1636)
    assert 8.0 < d < 11.0


def test_find_alternatives_filters_by_score_and_distance():
    target = _region("1", "대상동", 35.150, 129.050)
    too_far = _region("2", "먼동", 35.500, 129.050)  # 약 39km, 범위 밖
    lower_score = _region("3", "낮은동", 35.151, 129.051)  # 가깝지만 점수가 더 낮음
    better_nearby = _region("4", "좋은동", 35.152, 129.052)  # 가깝고 점수도 높음

    all_scores = {
        "1": _score_result(40),
        "2": _score_result(90),
        "3": _score_result(30),
        "4": _score_result(70),
    }
    region_by_id = {"1": target, "2": too_far, "3": lower_score, "4": better_nearby}

    result = find_alternatives(target, 40, all_scores, region_by_id)

    assert [a.region.region_id for a in result] == ["4"]


def test_no_cycle_between_two_alternatives():
    """A(낮은 점수)가 B(높은 점수)를 대안으로 추천했다면, B 입장에서 다시
    A를 대안으로 추천하는 일은 없어야 한다 — "점수가 더 높은 곳만" 조건이
    있으면 A>B와 B>A가 동시에 성립할 수 없어 수학적으로 순환이 불가능하다.
    실제 재현 시나리오(부전2동 50점 -> 전포2동 56점)를 그대로 본떴다."""
    seomyeon = _region("1", "부전2동", 35.1554, 129.0586)
    jeonpo = _region("2", "전포2동", 35.1600, 129.0650)  # 3km 이내
    all_scores = {"1": _score_result(50), "2": _score_result(56)}
    region_by_id = {"1": seomyeon, "2": jeonpo}

    seomyeon_alternatives = find_alternatives(seomyeon, 50, all_scores, region_by_id)
    assert any(a.region.region_id == "2" for a in seomyeon_alternatives)

    jeonpo_alternatives = find_alternatives(jeonpo, 56, all_scores, region_by_id)
    assert all(a.region.region_id != "1" for a in jeonpo_alternatives)


def test_find_alternatives_includes_breakdown_for_llm_grounding():
    target = _region("1", "대상동", 35.150, 129.050)
    better_nearby = _region("2", "좋은동", 35.151, 129.051)
    all_scores = {"1": _score_result(40, 경쟁강도=30), "2": _score_result(70, 경쟁강도=90)}
    region_by_id = {"1": target, "2": better_nearby}

    result = find_alternatives(target, 40, all_scores, region_by_id)

    assert result[0].breakdown.경쟁강도 == 90  # 대안 지역 고유의 breakdown이 그대로 담겨야 함


def test_find_alternatives_sorts_by_distance_and_caps_at_three():
    target = _region("0", "대상동", 35.150, 129.050)
    region_by_id = {"0": target}
    all_scores = {"0": _score_result(30)}
    # 0.01도씩 떨어진 지점을 4곳 만든다 (전부 점수가 대상보다 높고, 3km 이내)
    for i in range(1, 5):
        rid = str(i)
        offset = i * 0.005
        region_by_id[rid] = _region(rid, f"후보{i}", 35.150 + offset, 129.050)
        all_scores[rid] = _score_result(50)

    result = find_alternatives(target, 30, all_scores, region_by_id)

    assert len(result) == MAX_ALTERNATIVES
    distances = [a.distance_km for a in result]
    assert distances == sorted(distances)
    assert result[0].region.region_id == "1"  # 가장 가까운 곳부터


def test_find_alternatives_respects_max_distance():
    target = _region("0", "대상동", 35.150, 129.050)
    just_outside = _region("1", "범위밖", 35.150 + 0.05, 129.050)  # 대략 5.5km, 범위 밖
    dist = haversine_km(35.150, 129.050, 35.150 + 0.05, 129.050)
    assert dist > MAX_DISTANCE_KM  # 테스트 전제 확인

    result = find_alternatives(
        target, 30, {"0": _score_result(30), "1": _score_result(90)}, {"0": target, "1": just_outside}
    )

    assert result == []


def test_find_alternatives_excludes_self():
    target = _region("0", "대상동", 35.150, 129.050)
    result = find_alternatives(target, 30, {"0": _score_result(90)}, {"0": target})
    assert result == []
