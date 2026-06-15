import requests
import csv
import time
from datetime import datetime, timedelta

API_KEY = "3IrxqoEVDAU1ysqlouU6sw=="
BASE_URL = "https://khoa.go.kr/oceandata/api/tidalCurrentAreaGeoJson/search.do"

PARAMS_BASE = {
    "ServiceKey": API_KEY,
    "MaxX": 126.7,
    "MinX": 126.1,
    "MaxY": 34.9,
    "MinY": 34.4,
    "Scale": 4000000,
    "ResultType": "json"
}

OUTPUT_FILE = "tidal_current_mokpo.csv"  # 기존 파일에 이어붙임
FIELDNAMES = ["datetime", "lat", "lon", "current_direct", "current_speed"]

def fetch_tidal_current(date_str, hour, minute, retry=3):
    params = {
        **PARAMS_BASE,
        "Date": date_str,
        "Hour": f"{hour:02d}",
        "Minute": f"{minute:02d}"
    }
    for attempt in range(retry):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=10)
            data = resp.json()
            records = []
            for feature in data.get("features", []):
                props = feature["properties"]
                records.append({
                    "datetime": f"{date_str} {hour:02d}:{minute:02d}",
                    "lat": props["lat"],
                    "lon": props["lon"],
                    "current_direct": props["current_direct"],
                    "current_speed": props["current_speed"],
                })
            return records
        except Exception as e:
            print(f"  재시도 {attempt+1}/{retry}: {e}")
            time.sleep(2)
    print(f"  최종 실패: {date_str} {hour:02d}:{minute:02d} → 건너뜀")
    return []

# 내일 하루치 (00:00 ~ 23:50, 10분 단위)
tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
times = [f"{h:02d}:{m:02d}" for h in range(24) for m in range(0, 60, 10)]

print(f"내일({tomorrow}) 데이터를 {OUTPUT_FILE} 에 추가합니다.")
print(f"예상 호출 수: {len(times)}회 / 예상 시간: {len(times) * 0.5 / 60:.0f}분")
print("=" * 50)

total_calls = 0
total_rows = 0

for t in times:
    hour, minute = int(t.split(":")[0]), int(t.split(":")[1])
    records = fetch_tidal_current(tomorrow, hour, minute)

    if records:
        # 헤더 없이 append 모드로 기존 파일에 추가
        with open(OUTPUT_FILE, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writerows(records)
        total_rows += len(records)

    total_calls += 1
    print(f"[{total_calls}/{len(times)}] {tomorrow} {t} → {len(records)}행 (누적 {total_rows}행)")
    time.sleep(0.5)

print(f"\n완료! {tomorrow} 데이터 {total_rows}행 추가됨 → {OUTPUT_FILE}")