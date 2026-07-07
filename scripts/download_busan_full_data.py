"""
부산 빅데이터 플랫폼(Big-데이터웨이브, data.busan.go.kr)에서
"일별 행정동 시간/업종 생활인구·소비매출 월별 일평균" 3종 데이터셋의
전체(1,000행 절단 없는) 원본 파일을 내려받아 CSV로 저장한다.

원인 요약:
- 기존에 프로젝트 폴더에 있던 3개 CSV는 플랫폼의 "SHEET(미리보기)" 그리드에서
  내보낸 blob: 다운로드였고, 이 그리드가 1,000행으로 잘려 있었다.
  (kMDItemWhereFroms 메타데이터로 확인: blob:https://data.busan.go.kr/... , Safari 다운로드)
- 반면 플랫폼의 selectFileData.do API가 반환하는 실제 원본 파일(XLSX)은
  절단 없이 전체 데이터(2023-01~2025-12, 부산 206개 행정동 전체)를 담고 있다.
- 이 데이터셋들은 "파일 데이터(F)" 유형이라 Open API(numOfRows/pageNo)가 없다.
  실제 전체 데이터를 얻는 방법은 selectFileData.do가 알려주는 downurl에서
  직접 파일을 내려받는 것이다.

사용법:
    python3 scripts/download_busan_full_data.py
"""

import json
import subprocess
import pandas as pd
from pathlib import Path

BASE = "https://data.busan.go.kr/bdip"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

# publicdatapk: 플랫폼 검색 API(/bdip/srh/getPublicDataListSearch.do)로 확인한 데이터셋 ID
DATASETS = {
    "PD_LP00003": "일별 행정동 시간 생활인구 월별 일평균.csv",
    "PD_CS00003": "일별 행정동 시간 소비매출 월별 일평균.csv",
    "PD_CS00004": "일별 행정동 업종 소비매출 월별 일평균.csv",
}

OUT_DIR = Path(__file__).resolve().parent.parent


def get_download_url(publicdatapk: str) -> str:
    body = json.dumps({"publicdatapk": publicdatapk})
    r = subprocess.run(
        ["curl", "-s", "-A", UA, "-X", "POST", f"{BASE}/opendata/selectFileData.do",
         "-H", "Content-Type: application/json", "-d", body],
        capture_output=True, text=True,
    )
    data = json.loads(r.stdout)
    return data["fileList"][0]["downurl"]


def download(url: str, dest_xlsx: Path) -> None:
    subprocess.run(["curl", "-sL", "-A", UA, url, "-o", str(dest_xlsx)], check=True)


def main():
    for pk, csv_name in DATASETS.items():
        print(f"[{pk}] 다운로드 URL 조회 중...")
        url = get_download_url(pk)
        print(f"[{pk}] {url}")

        tmp_xlsx = OUT_DIR / f"_tmp_{pk}.xlsx"
        download(url, tmp_xlsx)

        df = pd.read_excel(tmp_xlsx)
        out_csv = OUT_DIR / csv_name
        df.to_csv(out_csv, index=False, encoding="utf-8-sig")
        tmp_xlsx.unlink()

        print(f"[{pk}] 저장 완료: {out_csv} ({len(df):,}행, "
              f"{df['행정동명'].nunique() if '행정동명' in df.columns else '?'}개 행정동)")


if __name__ == "__main__":
    main()
