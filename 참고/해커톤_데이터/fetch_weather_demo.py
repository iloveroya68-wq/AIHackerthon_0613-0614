"""
DRIFT - 기상 단기예보 수집 (6/11~14, 72시간)
기상청 VilageFcstInfoService_2.0
목포 격자: nx=50, ny=76
필요 항목: VEC(풍향), WSD(풍속), WAV(파고)
"""

import requests
import pandas as pd
import os

SERVICE_KEY = "c5ef9f73d2ffd1c4e3169dbea97957fdb068b9652438d37d9416cac294559f38"
BASE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
OUTPUT_DIR = "data"

# 오늘(6/11) 0500 발표본 기준으로 최대 72시간 예보
BASE_DATE = "20260611"
BASE_TIME = "0500"
TARGET = {"VEC", "WSD", "WAV", "TMP"}


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    params = {
        "serviceKey": SERVICE_KEY,
        "pageNo":     1,
        "numOfRows":  1000,
        "dataType":   "JSON",
        "base_date":  BASE_DATE,
        "base_time":  BASE_TIME,
        "nx":         50,
        "ny":         76,
    }

    resp = requests.get(BASE_URL, params=params, timeout=30)
    data = resp.json()
    items = data["response"]["body"]["items"]["item"]

    # 시간대별로 묶기
    time_map = {}
    for item in items:
        cat = item["category"]
        if cat not in TARGET:
            continue
        key = f"{item['fcstDate']}_{item['fcstTime']}"
        if key not in time_map:
            time_map[key] = {
                "fcst_date": item["fcstDate"],
                "fcst_time": item["fcstTime"],
            }
        time_map[key][cat] = item["fcstValue"]

    rows = []
    for key, val in sorted(time_map.items()):
        d = val["fcst_date"]
        t = val["fcst_time"]
        timestamp = f"{d[:4]}-{d[4:6]}-{d[6:]} {t[:2]}:{t[2:]}"
        rows.append({
            "timestamp":      timestamp,
            "wind_dir_deg":   _safe(val.get("VEC")),
            "wind_speed_mps": _safe(val.get("WSD")),
            "wave_height_m":  _safe(val.get("WAV")),
            "air_temp_c":     _safe(val.get("TMP")),
        })

    df = pd.DataFrame(rows)
    path = os.path.join(OUTPUT_DIR, "weather_forecast.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"✅ 저장: {path} ({len(df)}행)")
    print(f"기간: {df['timestamp'].min()} ~ {df['timestamp'].max()}")
    print(df.head(5).to_string())


def _safe(val):
    try:
        return float(val)
    except:
        return None


if __name__ == "__main__":
    main()