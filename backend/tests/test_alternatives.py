from app.alternatives import MAX_ALTERNATIVES, MAX_DISTANCE_KM, find_alternatives, haversine_km
from app.schemas import RegionInfo


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

    all_scores = {"1": 40, "2": 90, "3": 30, "4": 70}
    region_by_id = {"1": target, "2": too_far, "3": lower_score, "4": better_nearby}

    result = find_alternatives(target, 40, all_scores, region_by_id)

    assert [a.region.region_id for a in result] == ["4"]


def test_find_alternatives_sorts_by_distance_and_caps_at_three():
    target = _region("0", "대상동", 35.150, 129.050)
    region_by_id = {"0": target}
    all_scores = {"0": 30}
    # 0.01도씩 떨어진 지점을 4곳 만든다 (전부 점수가 대상보다 높고, 3km 이내)
    for i in range(1, 5):
        rid = str(i)
        offset = i * 0.005
        region_by_id[rid] = _region(rid, f"후보{i}", 35.150 + offset, 129.050)
        all_scores[rid] = 50

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

    result = find_alternatives(target, 30, {"0": 30, "1": 90}, {"0": target, "1": just_outside})

    assert result == []


def test_find_alternatives_excludes_self():
    target = _region("0", "대상동", 35.150, 129.050)
    result = find_alternatives(target, 30, {"0": 90}, {"0": target})
    assert result == []
