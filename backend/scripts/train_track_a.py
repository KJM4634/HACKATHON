"""
Track A(PRD 3.3): 일반음식점표준데이터의 실제 인허가일자/폐업일자를 라벨로 써서
"음식점(한식)" 업종의 3년 내 폐업위험을 예측하는 로지스틱회귀/랜덤포레스트를 학습한다.

카페/편의점/미용실은 이 데이터셋의 인허가 카테고리에 없어 실제 라벨이 없으므로
학습 대상에서 제외 — Track B 가중합만 계속 사용(scoring.py). pseudo-label은 쓰지 않음.

라벨: 인허가일자 기준 3년(1095일) 이내 폐업 = 1(폐업위험), 3년 이상 생존(계속 영업
중이거나 3년을 넘겨 살다 나중에 폐업) = 0. 아직 3년이 안 된 영업중 매장은 결과를
모르므로(censoring) 제외.

피처(전부 행정동 단위 지표, 매장 개별 속성 없음 — scoring.py의 Track B와 동일한
데이터 소스):
  - 총방문인구: 행정동 24시간 평균방문인구수 합
  - 구총인구수: 소속 구 인구(행정동 단위 데이터 없음, Track B와 동일한 한계)
  - 동일업종_경쟁업체수: 상가정보 기준 해당 행정동의 한식 업체 수(현재 스냅샷, 라벨과 무관한
    별도 데이터라 행별 리크 없음)
  - 동일업종_전체폐업률: 그 행정동의 한식 업체 중 "역대" 폐업 비율(closed/(closed+active)).
    자기 자신을 그 비율 계산에서 빼는 leave-one-out으로 만든다 — 안 그러면 폐업한 매장은
    자기 자신이 분자에 포함돼 라벨과 직접 연결되는 리크가 생긴다.

Track B의 ClosureStats.폐업률(최근 1년 기준, "오늘" 시점 스냅샷)과는 다른 정의다 —
그건 오늘 창업하는 사용자를 위한 "현재" 경쟁 상황 지표이고, 여기서는 학습 데이터가
수십 년에 걸쳐 있어 시점이 고정된 "역대 폐업률"을 써야 미래 시점 정보가 과거 라벨에
새지 않는다.

실행: cd backend && uv run python scripts/train_track_a.py
산출물: backend/app/ml/artifacts/track_a_음식점.joblib (모델), track_a_음식점_meta.json (지표/피처명)
"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_provider.local.foot_traffic_loader import get_foot_traffic_latest_month
from app.data_provider.local.population_loader import get_population_by_gu
from app.data_provider.local.restaurant_loader import get_restaurants_with_admin_dong
from app.data_provider.local.sanggabu_loader import get_sanggabu_busan

_WINDOW = pd.Timedelta(days=3 * 365)
_ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "app" / "ml" / "artifacts"
_UPTAE = "한식"
_FEATURE_COLUMNS = ["총방문인구", "구총인구수", "동일업종_경쟁업체수", "동일업종_전체폐업률"]


def _load_hansik() -> pd.DataFrame:
    df = get_restaurants_with_admin_dong()
    busan = df[(df["시도명"] == "부산광역시") & df["행정동코드"].notna()].copy()
    hansik = busan[busan["업태구분명"] == _UPTAE].copy()
    hansik["행정동코드"] = hansik["행정동코드"].astype("int64")
    hansik["인허가일자"] = pd.to_datetime(hansik["인허가일자"], errors="coerce")
    hansik["폐업일자"] = pd.to_datetime(hansik["폐업일자"], errors="coerce")
    return hansik


def _build_labels(hansik: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    closed = hansik[hansik["영업상태명"] == "폐업"].copy()
    closed["생존기간"] = closed["폐업일자"] - closed["인허가일자"]
    closed = closed[closed["생존기간"].notna() & (closed["생존기간"] >= pd.Timedelta(0))]
    closed["label"] = (closed["생존기간"] <= _WINDOW).astype(int)

    active = hansik[hansik["영업상태명"] == "영업/정상"].copy()
    active["영업기간"] = now - active["인허가일자"]
    active = active[active["영업기간"] >= _WINDOW]
    active["label"] = 0

    labeled = pd.concat([closed, active], ignore_index=False)
    return labeled[["행정동코드", "영업상태명", "label"]]


def _historical_closure_rate_leave_one_out(hansik: pd.DataFrame, labeled: pd.DataFrame) -> pd.Series:
    """행정동별 역대 폐업률(closed/(closed+active)), 각 행 자신은 분모/분자에서 제외."""
    closed_total = hansik[hansik["영업상태명"] == "폐업"].groupby("행정동코드").size()
    active_total = hansik[hansik["영업상태명"] == "영업/정상"].groupby("행정동코드").size()

    dong = labeled["행정동코드"]
    closed_count = dong.map(closed_total).fillna(0)
    active_count = dong.map(active_total).fillna(0)

    is_closed_row = (labeled["영업상태명"] == "폐업").astype(int)
    is_active_row = (labeled["영업상태명"] == "영업/정상").astype(int)
    closed_count_loo = closed_count - is_closed_row
    active_count_loo = active_count - is_active_row

    denom = closed_count_loo + active_count_loo
    rate = (closed_count_loo / denom.where(denom > 0, np.nan)) * 100
    return rate.fillna(rate.mean())


def _dong_level_features() -> pd.DataFrame:
    """행정동코드(8자리) -> 총방문인구/구총인구수/동일업종_경쟁업체수. 라벨과 무관, 206개 행정동당 1회 계산."""
    sanggabu = get_sanggabu_busan()
    dong_lookup = (
        sanggabu.groupby("행정동코드").agg(행정동명=("행정동명", "first"), 시군구명=("시군구명", "first")).reset_index()
    )

    competitor_count = (
        sanggabu[sanggabu["표준산업분류명"].str.contains(_UPTAE, na=False)]
        .groupby("행정동코드")
        .size()
        .rename("동일업종_경쟁업체수")
    )

    foot_traffic = get_foot_traffic_latest_month()
    visits = foot_traffic.groupby("행정동코드")["평균방문인구수"].sum().rename("총방문인구_10자리")

    population_by_gu = get_population_by_gu()

    dong_lookup = dong_lookup.merge(competitor_count, on="행정동코드", how="left")
    dong_lookup["동일업종_경쟁업체수"] = dong_lookup["동일업종_경쟁업체수"].fillna(0)

    # 방문인구 CSV는 10자리(행정동) 코드, 상가/일반음식점은 8자리 -> 10자리 = 8자리 * 100
    dong_lookup["행정동코드_10"] = dong_lookup["행정동코드"] * 100
    dong_lookup = dong_lookup.merge(
        visits, left_on="행정동코드_10", right_index=True, how="left"
    ).rename(columns={"총방문인구_10자리": "총방문인구"})
    dong_lookup["총방문인구"] = dong_lookup["총방문인구"].fillna(dong_lookup["총방문인구"].mean())

    dong_lookup["구총인구수"] = dong_lookup["시군구명"].map(lambda gu: population_by_gu[gu].총인구수)

    return dong_lookup.set_index("행정동코드")[["총방문인구", "구총인구수", "동일업종_경쟁업체수"]]


def build_dataset() -> tuple[pd.DataFrame, pd.Series]:
    now = pd.Timestamp.now()
    hansik = _load_hansik()
    labeled = _build_labels(hansik, now)

    labeled = labeled.copy()
    labeled["동일업종_전체폐업률"] = _historical_closure_rate_leave_one_out(hansik, labeled)

    dong_features = _dong_level_features()
    labeled = labeled.join(dong_features, on="행정동코드")
    labeled = labeled.dropna(subset=_FEATURE_COLUMNS)

    X = labeled[_FEATURE_COLUMNS]
    y = labeled["label"]
    return X, y


def train_and_evaluate(X: pd.DataFrame, y: pd.Series) -> dict:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    candidates = {
        "logistic_regression": Pipeline(
            [
                ("scaler", StandardScaler()),
                ("clf", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)),
            ]
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200, max_depth=6, class_weight="balanced", random_state=42, n_jobs=-1
        ),
    }

    results = {}
    for name, model in candidates.items():
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        proba = model.predict_proba(X_test)[:, 1]
        results[name] = {
            "model": model,
            "accuracy": accuracy_score(y_test, pred),
            "auc": roc_auc_score(y_test, proba),
            "precision": precision_score(y_test, pred),
            "recall": recall_score(y_test, pred),
        }

    return results, (X_train, X_test, y_train, y_test)


def main() -> None:
    print("=== Track A 학습 데이터 구성 ===")
    X, y = build_dataset()
    print(f"표본 수: {len(X)}  (폐업위험 {int(y.sum())} / 생존 {int((1 - y).sum())}, "
          f"양성비율 {y.mean() * 100:.1f}%)")
    print(f"피처: {_FEATURE_COLUMNS}")
    print()

    results, _ = train_and_evaluate(X, y)

    print("=== 모델 성능 (test set) ===")
    for name, r in results.items():
        print(
            f"{name}: accuracy={r['accuracy']:.3f} auc={r['auc']:.3f} "
            f"precision={r['precision']:.3f} recall={r['recall']:.3f}"
        )

    best_name = max(results, key=lambda n: results[n]["auc"])
    best_model = results[best_name]["model"]
    print(f"\nAUC 기준 최고 모델: {best_name} -> scoring.py에 연결할 모델로 저장")

    _ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, _ARTIFACT_DIR / "track_a_음식점.joblib")
    meta = {
        "model_name": best_name,
        "feature_columns": _FEATURE_COLUMNS,
        "window_days": _WINDOW.days,
        "metrics": {k: {m: v for m, v in r.items() if m != "model"} for k, r in results.items()},
        "n_samples": len(X),
        "positive_rate": float(y.mean()),
    }
    (_ARTIFACT_DIR / "track_a_음식점_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"저장 완료: {_ARTIFACT_DIR}")


if __name__ == "__main__":
    main()
