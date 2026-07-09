from curl_cffi import requests
import json
import time  # 봇 차단을 피하기 위해 쉬는 시간을 주기 위한 모듈
import pandas as pd

def get_naver_real_estate_all_pages():
    url = "https://new.land.naver.com/api/articles"
    
    headers = {
        "accept": "*/*",
        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        # 🚨 주의: authorization과 cookie는 너의 VIP 출입증 값 그대로 유지해야 해!
        "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IlJFQUxFU1RBVEUiLCJpYXQiOjE3ODM1OTc2ODAsImV4cCI6MTc4MzYwODQ4MH0.hkWr-d7rgqpqba-coVafTHIxtgOUEdmnuzkO7nToIZo",
        "cookie": "NAC=Y6dcBIRLMmh8; NNB=RH7TAVTAJ44WU; NACT=1; nid_inf=-1217963060; NID_AUT=ra/IWd5QiHH1CO9EJ674k1s0Apl5FOALYaYLT4+WdVr6RTooN37YLxteaD3Qu/iX; _ga=GA1.1.1058418056.1783597279; SRT30=1783597279; _ga_451MFZ9CFM=GS2.1.s1783597278$o1$g1$t1783597396$j60$l0$h0; _fwb=246gJvp8jTMxO6hF7SAxsIK.1783597397610; nhn.realestate.article.rlet_type_cd=A01; nhn.realestate.article.trade_type_cd=\"\"; nhn.realestate.article.ipaddress_city=2600000000; _fwb=168FVOh5xtcYRmsGuM2hzDI.1783597426572; realestate.beta.lastclick.cortar=4128111900; REALESTATE=Thu%20Jul%2009%202026%2020%3A48%3A00%20GMT%2B0900%20(Korean%20Standard%20Time); PROP_TEST_KEY=1783597680504.3db1b9ca6346a5294fbe17e31019c137f88e0b6896c0032275de93b575d52d5a; PROP_TEST_ID=66f6dc94cfb9c43b8d17a7ef68b36afd45e1f6204ddc8081c456f3b86466a4be; NID_SES=AAABp/0IQAqzHMS8pNyCeNHizT5/OWEwAMSBQJDqA3PR2srSzHgRPw2H9WnfETC+NE72gA6OlCcjJPN9FSW3f9Nqr7mz5m7cTytoXqNpbBm4thLPPX2GBu2wpkoPTTKngLwOlPiKXzVGJy8YTzfj4sUke8+2YMkM4VX4orJBCuZnvQV+6xMw+C37f3hpUu2CT3XYCQ1Q1/x1O3nvVR1JrFVFiPgbrKnyU5QGjVTTNLJoK/IGaDLNaJ/PdSMz/YhMy0VqaoESsn20EpGwvSat5//LqPcFyAAJdsE15cb57//jHES3UKv2cTXfiHqtkoGwpxugxcirmzqpEyUCVTQttU77XFaljSMZbRB5NpAVlfqjmfcsJxmEguEq3IV6HP2AZU3p+HbFT/AHTCiTTbTTpCAH+6l4badAiGSZWGjcPJcDNR2yPr7EoS6kfv958WsIRyXVUFid2FbHFJfINt+W9NXkeSFkQz9ofQQSoJCzu4YpoRjPEBAMDxdeL+adTsBMKBXVFiVfp7B7RD4IyZ7X4BtMMRC/fe7M9TwJJogxjeR7i2HOQwBmNr1kEvyF9M0SWXN+DQ==; SRT5=1783598588; BUC=_Gw2cu84NX7vaZ8YjmmKwjgD5zqABDkUDjbNlYJjKUw=",
        "referer": "https://new.land.naver.com/offices",
        "sec-ch-ua": "\"Chromium\";v=\"122\", \"Not(A:Brand\";v=\"24\", \"Google Chrome\";v=\"122\"",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    all_articles = []
    page = 1

    print("🚀 서면 상가 데이터 전체 수집을 시작합니다...")

    while True:
        print(f"📄 {page}페이지 수집 중...")
        
        params = {
            "cortarNo": "2623010300",
            "zoom": "15",
            "realEstateType": "SG:SMS:GJCG:APTHGJ:GM:TJ",
            "tradeType": "B2",
            "tag": "::::::::",
            "rentPriceMin": "0",
            "rentPriceMax": "900000000",
            "priceMin": "0",
            "priceMax": "900000000",
            "areaMin": "0",
            "areaMax": "900000000",
            "showArticle": "false",
            "sameAddressGroup": "false",
            "priceType": "RETAIL",
            "leftLon": "129.0500000",
            "rightLon": "129.0650000",
            "topLat": "35.1600000",
            "bottomLat": "35.1500000",
            "page": str(page)  # 숫자를 올려가며 페이지를 요청
        }

        try:
            response = requests.get(url, params=params, headers=headers, impersonate="chrome110", timeout=10)
            
            if response.status_code != 200:
                print("❌ 서버 에러 발생으로 중단합니다.")
                break
                
            data = response.json()
            
            # 데이터 뭉치 안에 'articleList'가 없거나 텅 비어있으면(마지막 페이지까지 다 봤으면) 반복문 탈출!
            if "articleList" not in data or len(data["articleList"]) == 0:
                print("✅ 모든 페이지 수집이 끝났습니다!")
                break
                
            # 가져온 매물 리스트를 전체 리스트에 합치기
            all_articles.extend(data["articleList"])
            page += 1
            
            # 서버에 너무 빠르게 요청하면 차단당할 수 있으므로 0.5초 대기
            time.sleep(0.5)
            
        except Exception as e:
            print(f"❌ 통신 에러 발생: {e}")
            break

    return all_articles

# ... (위쪽 get_naver_real_estate_all_pages 함수는 그대로 둠) ...

articles = get_naver_real_estate_all_pages()

print(f"\n🎉 빙고! 서면 지역에서 총 매물 {len(articles)}개를 싹쓸이했습니다!\n")

parsed_data = []

for item in articles:
    # 1. 월세 파싱 (콤마 제거)
    raw_rent = str(item.get("rentPrc", "0")).replace(",", "")
    rent = int(raw_rent) if raw_rent.isdigit() else 0
    
    # 2. 보증금 파싱 ("1억 5,000" 같은 한글 처리)
    raw_deposit = str(item.get("dealOrWarrantPrc", "0")).replace(" ", "").replace(",", "")
    deposit = 0
    if "억" in raw_deposit:
        parts = raw_deposit.split("억")
        eok = int(parts[0]) if parts[0].isdigit() else 0
        man = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        deposit = (eok * 10000) + man  # 1억 = 10000만 원
    else:
        deposit = int(raw_deposit) if raw_deposit.isdigit() else 0
        
    # 3. 면적 및 좌표 파싱 (변경된 Key 적용)
    area = float(item.get("area2", 0))  # 전용면적
    lat = item.get("latitude")
    lng = item.get("longitude")
    
    name = item.get("articleName", "이름없음")
    floor = item.get("floorInfo", "층수모름")
    
    # 1평 = 3.3㎡ (평당 월세 계산)
    pyeong = area / 3.3
    rent_per_pyeong = int(rent / pyeong) if pyeong > 0 else 0
    
    # 안전하게 좌표가 있는 데이터만 저장
    if lat and lng:
        parsed_data.append({
            "매물명": name,
            "층수": floor,
            "보증금": deposit,
            "월세": rent,
            "면적_m2": area,
            "평당월세": rent_per_pyeong,
            "lat": float(lat),
            "lng": float(lng)
        })

# DataFrame으로 변환 후 CSV 저장
df = pd.DataFrame(parsed_data)
df.to_csv("seomyeon_rent_data.csv", index=False, encoding="utf-8-sig")
print(f"💾 성공! 총 {len(parsed_data)}개의 데이터가 'seomyeon_rent_data.csv' 파일로 저장되었습니다!")