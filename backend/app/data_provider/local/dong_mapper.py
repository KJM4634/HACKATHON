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

최근접 매칭은 scipy.spatial.KDTree로 한다. 법정동 하나의 면적이 좁아
위도 변화에 따른 경도 1도당 거리 왜곡이 무시할 수준이므로, 위경도를
그 법정동 참조점들의 평균 위도로 보정한 평면(lon*cos(mean_lat), lat)에
투영해 트리를 만든다 — 진짜 지리좌표계 없이도 최근접 순서는 지오데식
거리(Geod.inv)와 실질적으로 같게 나온다(회귀 테스트로 확인).
"""

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.spatial import KDTree


@dataclass(frozen=True)
class AdminDong:
    행정동코드: str
    행정동명: str


class _AmbiguousGroup:
    """법정동 하나에 대한 KDTree 참조 인덱스."""

    __slots__ = ("tree", "행정동코드", "행정동명", "ref_lat")

    def __init__(self, lon: np.ndarray, lat: np.ndarray, 행정동코드: np.ndarray, 행정동명: np.ndarray):
        self.ref_lat = float(lat.mean())
        xy = _project(lon, lat, self.ref_lat)
        self.tree = KDTree(xy)
        self.행정동코드 = 행정동코드
        self.행정동명 = 행정동명

    def nearest(self, lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        xy = _project(lon, lat, self.ref_lat)
        _, idx = self.tree.query(xy)
        return self.행정동코드[idx], self.행정동명[idx]

    def leave_one_out_accuracy(self) -> float:
        """참조점 각각을 자기 자신을 뺀 나머지로 다시 맞혀보고 정확도를 계산.
        이 클래스가 실제로 쓰는 KDTree(및 투영)를 그대로 검증한다."""
        _, idx = self.tree.query(self.tree.data, k=2)
        own_idx = np.arange(len(self.행정동코드))
        other_idx = np.where(idx[:, 0] == own_idx, idx[:, 1], idx[:, 0])
        predicted = self.행정동코드[other_idx]
        return float((predicted == self.행정동코드).mean())


def _project(lon: np.ndarray, lat: np.ndarray, ref_lat: float) -> np.ndarray:
    scale = math.cos(math.radians(ref_lat))
    return np.column_stack([np.asarray(lon, dtype="float64") * scale, np.asarray(lat, dtype="float64")])


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

        self._ambiguous_groups: dict[tuple[str, str], _AmbiguousGroup] = {}
        for sigungu, legal_dong in ambiguous_keys:
            pts = sanggabu.loc[
                (sanggabu["시군구명"] == sigungu) & (sanggabu["법정동명"] == legal_dong),
                ["경도", "위도", "행정동코드", "행정동명"],
            ].dropna(subset=["경도", "위도"])
            if pts.empty:
                continue
            self._ambiguous_groups[(sigungu, legal_dong)] = _AmbiguousGroup(
                pts["경도"].to_numpy(),
                pts["위도"].to_numpy(),
                pts["행정동코드"].to_numpy(),
                pts["행정동명"].to_numpy(),
            )

        self.sigungu_names: set[str] = set(combos["시군구명"])
        self.legal_dong_by_sigungu: dict[str, set[str]] = {
            sigungu: set(combos.loc[combos["시군구명"] == sigungu, "법정동명"])
            for sigungu in self.sigungu_names
        }
        self.ambiguous_keys: set[tuple[str, str]] = set(self._ambiguous_groups.keys())

    def is_ambiguous(self, sigungu: str, legal_dong: str) -> bool:
        return (sigungu, legal_dong) in self._ambiguous_groups

    def lookup_unambiguous(self, sigungu: str, legal_dong: str) -> AdminDong | None:
        return self._unambiguous.get((sigungu, legal_dong))

    def assign(self, sigungu: str, legal_dong: str, lon: float, lat: float) -> AdminDong | None:
        key = (sigungu, legal_dong)
        if key in self._unambiguous:
            return self._unambiguous[key]

        group = self._ambiguous_groups.get(key)
        if group is None or pd.isna(lon) or pd.isna(lat):
            return None

        codes, names = group.nearest(np.array([lon]), np.array([lat]))
        return AdminDong(codes[0], names[0])

    def assign_many(
        self, sigungu: str, legal_dong: str, lon: np.ndarray, lat: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray] | None:
        """ambiguous 그룹 하나에 속한 여러 지점을 한 번의 KDTree 질의로 배정.

        (좌표 결측 필터링은 호출측 책임 — 여기 들어오는 lon/lat엔 NaN이 없어야 한다.)"""
        key = (sigungu, legal_dong)
        group = self._ambiguous_groups.get(key)
        if group is None:
            return None
        return group.nearest(lon, lat)

    def leave_one_out_accuracy(self, sigungu: str, legal_dong: str) -> float | None:
        """검증용: 이 법정동에서 실제 KDTree 배정 로직의 leave-one-out 정확도."""
        group = self._ambiguous_groups.get((sigungu, legal_dong))
        if group is None:
            return None
        return group.leave_one_out_accuracy()


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
