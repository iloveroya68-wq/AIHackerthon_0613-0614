"""
DRIFT - 해양기상 데이터 수집
기상청 API허브 sea_obs.php / 목포 STN=530350

파싱 확인된 버전:
parts: ['N','TM','STN_ID','STN_KO','LON','LAT','WH','WD','WS','WS_GST','TW','TA','PA','HM','FLAG','']
index:   0    1     2        3       4     5     6    7    8     9       10   11   12   13   14    15
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import time, os

AUTH_KEY   = "3CBwDRneSdCgcA0Z3lnQdw"
STN_ID     = "530350"
OUTPUT_DIR = "data"
BASE_URL   = "https://apihub.kma.go.kr/api/typ01/url/sea_obs.php"

def safe(val):
    try:
        v = float(val)
        return None if v == -99.0 else v
    except:
        return None

def fetch_one_hour(dt: datetime, retry: int = 3):
    params = {
        "tm":      dt.strftime("%Y%m%d%H%M"),
        "stn":     STN_ID,
        "help":    0,
        "authKey": AUTH_KEY,
    }
    for attempt in range(1, retry + 1):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()

            for line in resp.text.splitlines():
                if not line.strip() or line.startswith("#") or "START" in line or "END" in line:
                    continue
                parts = [p.strip().rstrip("=").strip() for p in line.split(",")]
                if len(parts) < 13:
                    continue

                return {
                    "timestamp":      dt.strftime("%Y-%m-%d %H:%M"),
                    "stn_id":         parts[2],
                    "stn_name":       parts[3],
                    "lon":            safe(parts[4]),
                    "lat":            safe(parts[5]),
                    "wave_height_m":  safe(parts[6]),   # WH
                    "wind_dir_deg":   safe(parts[7]),   # WD
                    "wind_speed_mps": safe(parts[8]),   # WS
                    "gust_mps":       safe(parts[9]),   # WS_GST
                    "water_temp_c":   safe(parts[10]),  # TW
                    "air_temp_c":     safe(parts[11]),  # TA
                    "pressure_hpa":   safe(parts[12]),  # PA
                }
            return None

        except Exception as e:
            if attempt < retry:
                time.sleep(2 * attempt)
            else:
                print(f"  ❌ {dt.strftime('%Y-%m-%d %H:%M')} 실패: {e}")
    return None

def collect_range(start: datetime, end: datetime, label: str) -> pd.DataFrame:
    all_rows = []
    current  = start
    total_h  = int((end - start).total_seconds() / 3600) + 1
    done     = 0

    print(f"\n[{label}] {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')} ({total_h}시간)")

    while current <= end:
        row = fetch_one_hour(current)
        if row:
            all_rows.append(row)
        done += 1
        if done % 240 == 0 or current == end:
            print(f"  진행: {done}/{total_h}시간 ({len(all_rows):,}건 수집)")
        current += timedelta(hours=1)
        time.sleep(0.3)

    return pd.DataFrame(all_rows)

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 과거 1년치
    df_past = collect_range(
        datetime(2025, 6, 10, 0, 0),
        datetime(2026, 6,  9, 23, 0),
        "과거 1년치"
    )
    if not df_past.empty:
        path = os.path.join(OUTPUT_DIR, "weather_past_1year.csv")
        df_past.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  ✅ 저장: {path} ({len(df_past):,}행)")

    # 데모 기간
    df_demo = collect_range(
        datetime(2026, 6, 12, 0, 0),
        datetime(2026, 6, 15, 23, 0),
        "데모 기간"
    )
    if not df_demo.empty:
        path = os.path.join(OUTPUT_DIR, "weather_demo.csv")
        df_demo.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  ✅ 저장: {path} ({len(df_demo):,}행)")

    # 합본
    df_all = pd.concat([df_past, df_demo], ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    path = os.path.join(OUTPUT_DIR, "weather_ALL.csv")
    df_all.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n✅ 합본: {path} (총 {len(df_all):,}행)")
    print("완료!")

if __name__ == "__main__":
    main()