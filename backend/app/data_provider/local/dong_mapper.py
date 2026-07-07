"""
법정동 -> 행정동 매핑.

일반음식점표준데이터에는 행정동 필드가 없고 주소 텍스트에 법정동명만 있다.
법정동 하나가 여러 행정동으로 쪼개진 경우(예: 부전동 -> 부전1동/부전2동)엔
주소 텍스트만으론 어느 행정동인지 구분할 수 없다.

행정동 경계 폴리곤 데이터가 없으므로, 상가(상권)정보에 이미 있는 실측
(법정동, 행정동, 경도, 위도)를 참조점으로 삼아 최근접 매칭으로 배정한다.
법정동이 행정동 하나에만 대응하면(대부분의 경우) 좌표 없이 바로 배정한다.

부산 기준 법정동 248개 중 55개가 분할 케이스이며, 데모 타겟 4곳 중
서면(부전동)/해운대(우동)/광안리(광안동) 3곳이 여기 해당한다
(남포동은 법정동 6개가 모두 남포동 행정동 하나로만 매핑돼 문제 없음).
"""

from dataclasses import dataclass

import pandas as pd
from pyproj import Geod

_GEOD = Geod(ellps="WGS84")


@dataclass(frozen=True)
class AdminDong:
    행정동코드: str
    행정동명: str


class LegalToAdminDongMapper:
    def __init__(self, sanggabu: pd.DataFrame):
        """sanggabu: 상가(상권)정보 DataFrame. 시군구명/법정동명/행정동코드/행정동명/경도/위도 필요."""
        key_cols = ["시군구명", "법정동명", "행정동코드", "행정동명"]
        combos = sanggabu[key_cols].drop_duplicates()

        admin_count = combos.groupby(["시군구명", "법정동명"])["행정동코드"].nunique()
        unambiguous_keys = admin_count[admin_count == 1].index
        ambiguous_keys = admin_count[admin_count > 1].index

        self._unambiguous: dict[tuple[str, str], AdminDong] = {}
        for sigungu, legal_dong in unambiguous_keys:
            row = combos[(combos["시군구명"] == sigungu) & (combos["법정동명"] == legal_dong)].iloc[0]
            self._unambiguous[(sigungu, legal_dong)] = AdminDong(row["행정동코드"], row["행정동명"])

        self._ambiguous_points: dict[tuple[str, str], pd.DataFrame] = {}
        for sigungu, legal_dong in ambiguous_keys:
            pts = sanggabu.loc[
                (sanggabu["시군구명"] == sigungu) & (sanggabu["법정동명"] == legal_dong),
                ["경도", "위도", "행정동코드", "행정동명"],
            ].dropna(subset=["경도", "위도"])
            self._ambiguous_points[(sigungu, legal_dong)] = pts

        self.sigungu_names: set[str] = set(combos["시군구명"])
        self.legal_dong_by_sigungu: dict[str, set[str]] = {
            sigungu: set(combos.loc[combos["시군구명"] == sigungu, "법정동명"])
            for sigungu in self.sigungu_names
        }
        self.ambiguous_keys: set[tuple[str, str]] = set(self._ambiguous_points.keys())

    def is_ambiguous(self, sigungu: str, legal_dong: str) -> bool:
        return (sigungu, legal_dong) in self._ambiguous_points

    def assign(self, sigungu: str, legal_dong: str, lon: float, lat: float) -> AdminDong | None:
        key = (sigungu, legal_dong)
        if key in self._unambiguous:
            return self._unambiguous[key]

        pts = self._ambiguous_points.get(key)
        if pts is None or pts.empty or pd.isna(lon) or pd.isna(lat):
            return None

        _, _, dist_m = _GEOD.inv(
            [lon] * len(pts), [lat] * len(pts), pts["경도"].to_numpy(), pts["위도"].to_numpy()
        )
        nearest = pts.iloc[dist_m.argmin()]
        return AdminDong(nearest["행정동코드"], nearest["행정동명"])


def parse_sigungu_and_legal_dong(
    address: object, mapper: LegalToAdminDongMapper
) -> tuple[str, str] | None:
    """주소 텍스트에서 시군구명, 법정동명 토큰을 찾는다. 못 찾으면 None.

    지번주소("...부산진구 부전동 200-1")와 도로명주소("...(부전동)") 형식을
    모두 다루기 위해 괄호/쉼표를 공백으로 바꾼 뒤 토큰 단위로 비교한다.
    """
    if not isinstance(address, str):
        return None

    cleaned = address.replace("(", " ").replace(")", " ").replace(",", " ")
    tokens = cleaned.split()

    sigungu = next((t for t in tokens if t in mapper.sigungu_names), None)
    if sigungu is None:
        return None

    candidates = mapper.legal_dong_by_sigungu.get(sigungu, set())
    legal_dong = next((t for t in tokens if t in candidates), None)
    if legal_dong is None:
        return None

    return sigungu, legal_dong
