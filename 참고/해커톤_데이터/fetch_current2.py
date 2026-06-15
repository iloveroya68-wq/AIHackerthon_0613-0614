"""
DRIFT - 목포구 조류 데이터 수집
obsCode=01MP-2 / 목포구 (lat: 34.75916, lon: 126.30444)
"""

import requests
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime, timedelta
import time, os

SERVICE_KEY = "c5ef9f73d2ffd1c4e3169dbea97957fdb068b9652438d37d9416cac294559f38"
OBS_CODE    = "01MP-2"
OUTPUT_DIR  = "data"
BASE_URL    = "https://apis.data.go.kr/1192136/crntFcstTime/GetCrntFcstTimeApiService"

DIR_TO_DEG = {
    "북": 0, "북북동": 22.5, "북동": 45, "동북동": 67.5,
    "동": 90, "동남동": 112.5, "남동": 135, "남남동": 157.5,
    "남": 180, "남남서": 202.5, "남서": 225, "서남서": 247.5,
    "서": 270, "서북서": 292.5, "북서": 315, "북북서": 337.5,
}

def fetch_one_day(date: datetime, retry: int = 3) -> list[dict]:
    params = {
        "serviceKey": SERVICE_KEY,
        "obsCode":    OBS_CODE,
        "reqDate":    date.strftime("%Y%m%d"),
        "min":        60,
        "numOfRows":  300,
    }
    for attempt in range(1, retry + 1):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            if root.findtext(".//resultCode") != "00":
                print(f"  ⚠ {date.strftime('%Y-%m-%d')} 오류: {root.findtext('.//resultMsg')}")
                return []
            rows = []
            for item in root.findall(".//item"):
                crdir = item.findtext("crdir", "").strip()
                crsp  = float(item.findtext("crsp", "0") or 0)
                rows.append({
                    "predcDt":           item.findtext("predcDt", ""),
                    "station":           item.findtext("obsvtrNm", ""),
                    "lat":               float(item.findtext("lat", "0")),
                    "lon":               float(item.findtext("lot", "0")),
                    "current_dir_str":   crdir,
                    "current_dir_deg":   DIR_TO_DEG.get(crdir, 0.0),
                    "current_speed_cms": crsp,
                    "current_speed_mps": round(crsp / 100, 4),
                })
            return rows
        except Exception as e:
            if attempt < retry:
                time.sleep(2 * attempt)
            else:
                print(f"  ❌ {date.strftime('%Y-%m-%d')} 실패: {e}")
    return []

def collect_range(start: datetime, end: datetime, label: str) -> pd.DataFrame:
    all_rows = []
    current  = start
    total    = (end - start).days + 1
    done     = 0
    print(f"\n[{label}] {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')} ({total}일)")
    while current <= end:
        rows = fetch_one_day(current)
        all_rows.extend(rows)
        done += 1
        if done % 30 == 0 or current == end:
            print(f"  진행: {done}/{total}일 ({len(all_rows):,}행 수집)")
        current += timedelta(days=1)
        time.sleep(0.5)
    return pd.DataFrame(all_rows)

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 과거 1년치
    df_past = collect_range(datetime(2025, 6, 10), datetime(2026, 6, 9), "목포구 과거 1년치")
    if not df_past.empty:
        path = os.path.join(OUTPUT_DIR, "current_mokpoku_past_1year.csv")
        df_past.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  ✅ 저장: {path} ({len(df_past):,}행)")

    # 데모 예보
    df_demo = collect_range(datetime(2026, 6, 12), datetime(2026, 6, 15), "목포구 데모 예보")
    if not df_demo.empty:
        path = os.path.join(OUTPUT_DIR, "current_mokpoku_demo.csv")
        df_demo.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  ✅ 저장: {path} ({len(df_demo):,}행)")

    # 합본
    df_all = pd.concat([df_past, df_demo], ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["predcDt"]).sort_values("predcDt").reset_index(drop=True)
    path = os.path.join(OUTPUT_DIR, "current_mokpoku_ALL.csv")
    df_all.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n✅ 합본: {path} (총 {len(df_all):,}행)")
    print("완료!")

if __name__ == "__main__":
    main()