"""
DRIFT - 기상 데이터 수집 (10분 단위)
기상청 API허브 sea_obs.php
관측소: 목포 (STN=530350)

응답 특성: "요청한 시간에서 -59분~00분 사이 자료 표출"
→ 10분 단위로 요청하면 각 시각의 실측값 반환
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


def fetch_one(dt: datetime, retry: int = 3):
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
                    "wind_dir_deg":   safe(parts[7]),
                    "wind_speed_mps": safe(parts[8]),
                    "wave_height_m":  safe(parts[6]),
                    "water_temp_c":   safe(parts[10]),
                    "air_temp_c":     safe(parts[11]),
                    "pressure_hpa":   safe(parts[12]),
                }
            return None
        except Exception as e:
            if attempt < retry:
                time.sleep(2 * attempt)
            else:
                print(f"  ❌ {dt.strftime('%Y-%m-%d %H:%M')} 실패: {e}")
    return None


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    start = datetime(2025, 6, 10, 0, 0)
    end   = datetime(2026, 6,  9, 23, 50)
    total = int((end - start).total_seconds() / 600) + 1  # 10분 단위
    done  = 0
    all_rows = []

    print(f"\n[목포 기상 10분 단위] {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')} ({total:,}회)")

    current = start
    while current <= end:
        row = fetch_one(current)
        if row:
            all_rows.append(row)
        done += 1
        if done % 1440 == 0 or current == end:  # 10일마다 출력
            print(f"  진행: {done:,}/{total:,} ({len(all_rows):,}건 수집)")
        current += timedelta(minutes=10)
        time.sleep(0.3)

    df = pd.DataFrame(all_rows)
    path = os.path.join(OUTPUT_DIR, "weather_10min_1year.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n✅ 저장: {path} ({len(df):,}행)")
    print("완료!")


if __name__ == "__main__":
    main()