# Modeling Input Dataset

이 폴더는 모델링팀 전달용 데이터 패키지입니다.

## 기준 기간

- 기준 사고일: `2023-09-23`
- 수집 목표 기간: `2023-03-23` ~ `2024-03-23`
- 의미: 사고 날짜 기준 앞뒤 6개월

현재 CMEMS 원본은 이 기간을 포함하는 더 넓은 범위(`2022-03-24` ~ `2024-03-24`)로 들어있고, KHOA 원본은 월 단위 파일 특성상 `2023-03-01` ~ `2024-03-31` 범위를 포함합니다.

## 추천 사용 순서

1. `processed/cmems/cmems_surface_current_hourly.csv`
   - `time`, `latitude`, `longitude`, `uo`, `vo`, `current_speed_mps`, `current_direction_deg`
   - Monte Carlo 입자 이동의 해류 입력

2. `processed/khoa/khoa_mokpo_weather_hourly.csv`
   - `timestamp`, `wind_speed_mps`, `wind_direction_deg`, `air_pressure_hpa`, `air_temperature_c`
   - 풍압 편류와 기상 피처 입력

3. `processed/leeway/leeway_coefficients.csv`
   - `object_key`, `leeway_rate`, `sigma`, `divergence_deg`
   - 표류체 유형별 leeway 계수

4. `processed/geo/land_mask.geojson`
   - 육지 충돌(stranding) 판정
   - 수색 polygon clipping

5. `processed/accidents/l3_synthetic_accidents.csv`
   - 발생 위치와 조류/풍 조건으로 생성한 합성 발견 좌표
   - 실제 사고 데이터가 아니므로 학습 파이프라인 검증/데모용으로 사용

## 주의

- `synthetic_found_lat`, `synthetic_found_lon`은 사용자 제공 L3 합성데이터의 가상 생성 좌표입니다.
- CMEMS CSV는 파일이 크므로 VS Code에서 직접 열기보다 DuckDB, pandas chunk, parquet 변환을 권장합니다.
- 원본 파일은 `raw/`에 보존했고, 모델링에는 `processed/` 파일을 우선 사용하면 됩니다.
