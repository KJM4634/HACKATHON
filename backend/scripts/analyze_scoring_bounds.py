"""
scoring.py의 정규화 상/하한을 산출한 근거를 재현하는 스크립트.

부산 206개 행정동 전체의 실측 분포(P5~P95)를 계산해 출력한다.
scoring.py의 _VISIT_POP_RANGE / _GU_POPULATION_RANGE / _COMPETITOR_COUNT_RANGE /
_CLOSURE_RATE_RANGE / _REVENUE_RANGE 값이 이 출력과 어긋나면 원본 데이터가
갱신됐다는 뜻이니 재산정이 필요하다.

실행: cd backend && uv run python3 scripts/analyze_scoring_bounds.py
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ 를 sys.path에 추가

from app.data_provider.local.consumption_loader import get_consumption_by_category_latest_month
from app.data_provider.local.foot_traffic_loader import get_foot_traffic_latest_month
from app.data_provider.local.population_loader import get_population_by_gu
from app.data_provider.local.restaurant_loader import get_restaurants_with_admin_dong
from app.data_provider.local.sanggabu_loader import get_sanggabu_busan

PERCENTILES = [0.05, 0.25, 0.5, 0.75, 0.95]


def main():
    print("=== 일 총 방문인구 (24h 합, 행정동당) ===")
    foot = get_foot_traffic_latest_month()
    visits = foot.groupby("행정동코드")["평균방문인구수"].sum()
    print(visits.quantile(PERCENTILES))
    print()

    print("=== 구 총인구수 (16개 구) ===")
    pop = get_population_by_gu()
    print(pd.Series({k: v.총인구수 for k, v in pop.items()}).sort_values())
    print()

    print("=== 업종별 경쟁업체수 (행정동당) ===")
    sanggabu = get_sanggabu_busan()
    all_dong = sanggabu["행정동코드"].unique()
    for cat, keyword in {"카페": "커피", "음식점": "한식", "편의점": "편의점", "미용실": "미용업"}.items():
        matched = sanggabu[sanggabu["표준산업분류명"].str.contains(keyword, na=False)]
        counts = matched.groupby("행정동코드").size().reindex(all_dong, fill_value=0)
        print(f"[{cat}]", counts.quantile(PERCENTILES).to_dict())
    print()

    print("=== 업종대분류별 매출(평균이용금액, 행정동당) ===")
    cons = get_consumption_by_category_latest_month()
    for bucket in ["음식/주점", "유통", "미용"]:
        sub = cons[cons["업종대분류"] == bucket]["평균이용금액"]
        print(f"[{bucket}]", sub.quantile(PERCENTILES).to_dict())
    print()

    print("=== 한식(일반음식점) 최근1년 폐업률 (행정동당, %) ===")
    df = get_restaurants_with_admin_dong()
    busan = df[(df["시도명"] == "부산광역시") & (df["업태구분명"] == "한식") & df["행정동코드"].notna()].copy()
    busan["폐업일자_dt"] = pd.to_datetime(busan["폐업일자"], errors="coerce")
    one_year_ago = datetime.now() - timedelta(days=365)

    rows = []
    for dong, g in busan.groupby("행정동코드"):
        active = (g["영업상태명"] == "영업/정상").sum()
        closed_recent = ((g["영업상태명"] == "폐업") & (g["폐업일자_dt"] >= one_year_ago)).sum()
        if active + closed_recent == 0:
            continue
        rows.append(closed_recent / (active + closed_recent) * 100)
    print(pd.Series(rows).quantile(PERCENTILES))


if __name__ == "__main__":
    main()
