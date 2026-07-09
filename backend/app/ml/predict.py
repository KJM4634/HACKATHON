"""
Track A(PRD 3.3): scripts/train_track_a.py에서 실제 라벨(인허가일자/폐업일자)로 학습한
'한식' 3년 내 폐업위험 모델을 스코어링 엔진에 연결한다.

한식만 실제 라벨이 있어 이 카테고리에만 적용한다 — "음식점"이 한식/중식/분식/
기타음식점 4개 서브카테고리로 나뉜 뒤에도 Track A 적용 범위는 그대로다(한식
서브탭을 선택했을 때만 노출). 카페/편의점/미용실/중식/분식/기타음식점은 라벨이
없어 pseudo-label 없이 Track B 가중합만 쓰고, available=False로 정직하게 표시한다.

모델 아티팩트 파일명(track_a_음식점.*)은 학습 당시("음식점"이 아직 나뉘기 전)
이름을 그대로 유지한다 — 재학습이 필요한 변경이 아니라 파일명 표기 문제일
뿐이라, 실제로 다시 훈련시키지 않는 한 이름을 바꿀 이유가 없다.
"""

import json
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

from app.data_provider.local.restaurant_loader import get_restaurants_with_admin_dong
from app.schemas import MarketData, TrackAPrediction

_ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
_UPTAE = "한식"
_SUPPORTED_CATEGORY = "한식"


@lru_cache
def _load_meta() -> dict:
    return json.loads((_ARTIFACT_DIR / "track_a_음식점_meta.json").read_text(encoding="utf-8"))


@lru_cache
def _load_model():
    return joblib.load(_ARTIFACT_DIR / "track_a_음식점.joblib")


@lru_cache
def _historical_closure_rate_by_dong() -> dict[int, float]:
    """행정동(8자리코드)별 한식 역대 폐업률(%) — 학습 때(train_track_a.py)와 같은 정의지만,
    여기서는 아직 존재하지 않는 신규 매장을 가정하므로 leave-one-out이 필요 없다."""
    df = get_restaurants_with_admin_dong()
    busan = df[(df["시도명"] == "부산광역시") & df["행정동코드"].notna()]
    hansik = busan[busan["업태구분명"] == _UPTAE]

    closed = hansik[hansik["영업상태명"] == "폐업"].groupby("행정동코드").size()
    active = hansik[hansik["영업상태명"] == "영업/정상"].groupby("행정동코드").size()

    rates: dict[int, float] = {}
    for code in set(closed.index) | set(active.index):
        c, a = closed.get(code, 0), active.get(code, 0)
        if c + a > 0:
            rates[int(code)] = round(c / (c + a) * 100, 2)
    return rates


def predict_track_a(market_data: MarketData, category: str) -> TrackAPrediction:
    if category != _SUPPORTED_CATEGORY:
        return TrackAPrediction(available=False)

    code8 = int(market_data.region.region_id) // 100
    rate = _historical_closure_rate_by_dong().get(code8)
    if rate is None:
        return TrackAPrediction(available=False)

    meta = _load_meta()
    total_visits = sum(h.평균방문인구수 for h in market_data.foot_traffic)
    raw_features = {
        "총방문인구": total_visits,
        "구총인구수": market_data.population.총인구수,
        "동일업종_경쟁업체수": market_data.competitors.total_count,
        "동일업종_전체폐업률": rate,
    }
    features = pd.DataFrame([[raw_features[col] for col in meta["feature_columns"]]], columns=meta["feature_columns"])

    model = _load_model()
    closure_probability = float(model.predict_proba(features)[0, 1])

    return TrackAPrediction(
        available=True,
        closure_risk_3yr=round(closure_probability, 3),
        model_name=meta["model_name"],
    )
