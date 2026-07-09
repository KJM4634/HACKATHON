from curl_cffi import requests
import json

url = "https://new.land.naver.com/api/articles"
params = {
    "cortarNo": "2623010300", "zoom": "15", "realEstateType": "SG:SMS:GJCG:APTHGJ:GM:TJ",
    "tradeType": "B2", "priceType": "RETAIL", "page": "1",
    "leftLon": "129.0500000", "rightLon": "129.0650000", "topLat": "35.1600000", "bottomLat": "35.1500000"
}

headers = {
    "accept": "*/*",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    # 🚨 본인의 인증 토큰(authorization, cookie)으로 반드시 교체해 줘!
    "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IlJFQUxFU1RBVEUiLCJpYXQiOjE3ODM1OTc2ODAsImV4cCI6MTc4MzYwODQ4MH0.hkWr-d7rgqpqba-coVafTHIxtgOUEdmnuzkO7nToIZo",
    "cookie": "NAC=Y6dcBIRLMmh8; NNB=RH7TAVTAJ44WU; NACT=1; nid_inf=-1217963060; NID_AUT=ra/IWd5QiHH1CO9EJ674k1s0Apl5FOALYaYLT4+WdVr6RTooN37YLxteaD3Qu/iX; _ga=GA1.1.1058418056.1783597279; SRT30=1783597279; _ga_451MFZ9CFM=GS2.1.s1783597278$o1$g1$t1783597396$j60$l0$h0; _fwb=246gJvp8jTMxO6hF7SAxsIK.1783597397610; nhn.realestate.article.rlet_type_cd=A01; nhn.realestate.article.trade_type_cd=\"\"; nhn.realestate.article.ipaddress_city=2600000000; _fwb=168FVOh5xtcYRmsGuM2hzDI.1783597426572; realestate.beta.lastclick.cortar=4128111900; REALESTATE=Thu%20Jul%2009%202026%2020%3A48%3A00%20GMT%2B0900%20(Korean%20Standard%20Time); PROP_TEST_KEY=1783597680504.3db1b9ca6346a5294fbe17e31019c137f88e0b6896c0032275de93b575d52d5a; PROP_TEST_ID=66f6dc94cfb9c43b8d17a7ef68b36afd45e1f6204ddc8081c456f3b86466a4be; NID_SES=AAABp/0IQAqzHMS8pNyCeNHizT5/OWEwAMSBQJDqA3PR2srSzHgRPw2H9WnfETC+NE72gA6OlCcjJPN9FSW3f9Nqr7mz5m7cTytoXqNpbBm4thLPPX2GBu2wpkoPTTKngLwOlPiKXzVGJy8YTzfj4sUke8+2YMkM4VX4orJBCuZnvQV+6xMw+C37f3hpUu2CT3XYCQ1Q1/x1O3nvVR1JrFVFiPgbrKnyU5QGjVTTNLJoK/IGaDLNaJ/PdSMz/YhMy0VqaoESsn20EpGwvSat5//LqPcFyAAJdsE15cb57//jHES3UKv2cTXfiHqtkoGwpxugxcirmzqpEyUCVTQttU77XFaljSMZbRB5NpAVlfqjmfcsJxmEguEq3IV6HP2AZU3p+HbFT/AHTCiTTbTTpCAH+6l4badAiGSZWGjcPJcDNR2yPr7EoS6kfv958WsIRyXVUFid2FbHFJfINt+W9NXkeSFkQz9ofQQSoJCzu4YpoRjPEBAMDxdeL+adTsBMKBXVFiVfp7B7RD4IyZ7X4BtMMRC/fe7M9TwJJogxjeR7i2HOQwBmNr1kEvyF9M0SWXN+DQ==; SRT5=1783598588; BUC=_Gw2cu84NX7vaZ8YjmmKwjgD5zqABDkUDjbNlYJjKUw=",
    "referer": "https://new.land.naver.com/offices",
    "sec-ch-ua": "\"Chromium\";v=\"122\", \"Not(A:Brand\";v=\"24\", \"Google Chrome\";v=\"122\"",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

response = requests.get(url, params=params, headers=headers, impersonate="chrome110")
data = response.json()

# 첫 번째 매물의 모든 Key와 데이터를 숨김없이 출력!
print(json.dumps(data["articleList"][0], indent=2, ensure_ascii=False))