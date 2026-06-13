# DRIFT 모델 엔진 구현 명세서

## 1. 목적

이 문서는 DRIFT 저장소에 실제 표류 예측 엔진을 구현하기 위한 기준 명세다.

구현 목표는 다음과 같다.

1. KHOA/KMA/CMEMS 환경 데이터를 수집한다.
2. 물리 기반 표류 중심점과 OpenDrift 입자 분포를 계산한다.
3. LightGBM으로 물리 모델의 위치 오차를 보정한다.
4. 입자 분포에서 60%, 80%, 95% 수색 구역을 생성한다.
5. 기존 `contracts.EnginePredictionResult` 형식으로 결과를 반환한다.
6. 모델이나 외부 데이터가 없어도 명시적인 fallback으로 동작한다.

이 명세는 별도 FastAPI 애플리케이션을 추가하지 않는다. 외부 API는 기존 Django REST Framework가 담당하고, 계산 로직은 독립적인 `drift_engine` 패키지로 구현한다.

---

## 2. 기존 구조와의 통합 원칙

### 2.1 단일 데이터 계약

모듈 간 요청과 응답은 반드시 다음 Pydantic 모델을 사용한다.

- 입력: `contracts.models.PredictionRequest`
- 출력: `contracts.models.EnginePredictionResult`
- 시간별 출력: `contracts.models.TimeStepResult`
- 위험 예측 출력: `contracts.models.RiskForecastResult`

`engine` 내부에 API 전용 request/response 모델을 다시 정의하지 않는다.

### 2.2 백엔드 결합 지점

Django 백엔드는 모델 구현을 직접 알지 않는다.

```python
from drift_engine import RealDriftEngine

result = RealDriftEngine().predict(request)
```

교체 지점은 `backend/apps/sar/engine_interface.py`의 `get_engine()` 하나로 유지한다.

### 2.3 실행 모드

```env
DRIFT_ENGINE=mock
```

- `mock`: 현재 `MockEngine` 사용
- `real`: `drift_engine.RealDriftEngine` 사용
- real 모드에서 모델 파일이 없으면 L1+L2만 실행
- real 모드에서 환경 데이터 조회가 실패하면 fallback 데이터 사용
- OpenDrift 자체가 실패하면 요청 전체를 성공으로 위장하지 않고 엔진 오류를 발생시킨다.

---

## 3. 목표 디렉터리 구조

```text
engine/
  pyproject.toml
  README.md
  backend/integrations/public_marine_data.py

  drift_engine/
    __init__.py
    engine.py
    config.py
    exceptions.py
    features.py
    l1_physics.py
    l2_monte_carlo.py
    l3_correction.py
    fusion.py
    search_zones.py
    geo.py

    opendrift_runner/
      __init__.py
      runner.py
      readers.py

  artifacts/
    model_metadata.json
    README.md

  scripts/
    generate_synthetic_dataset.py
    train_l3_model.py
    evaluate_l3_model.py

  tests/
    test_l1_physics.py
    test_l2_monte_carlo.py
    test_l3_fallback.py
    test_search_zones.py
    test_real_engine_contract.py
```

`*.pkl`, `*.joblib`, `*.csv`는 저장소의 `.gitignore` 대상이다. 실제 모델과 학습 데이터는 이미지 빌드, 배포 볼륨 또는 object storage를 통해 공급한다. `model_metadata.json`만 버전 관리한다.

---

## 4. 공개 인터페이스

### 4.1 엔진 클래스

```python
class RealDriftEngine:
    def predict(self, request: PredictionRequest) -> EnginePredictionResult:
        ...
```

`engine/drift_engine/__init__.py`는 `RealDriftEngine`만 공개해도 충분하다.

### 4.2 처리 순서

```text
PredictionRequest
  -> 입력 검증
  -> 환경 데이터 조회
  -> L1 물리 표류 벡터 계산
  -> L2 OpenDrift/Monte Carlo 실행
  -> L3 LightGBM 위치 잔차 예측
  -> 중심점 및 입자 보정
  -> 확률 수색 구역 생성
  -> 시간별 TimeStepResult 생성
  -> EnginePredictionResult 검증 및 반환
```

---

## 5. 환경 데이터 계층

실시간 외부 API 호출은 `backend/integrations/`에서 수행하고, engine에는 정규화된
`EnvironmentData` provider를 주입한다.

### 5.1 내부 데이터 구조

```python
@dataclass
class EnvironmentData:
    current_u_ms: float
    current_v_ms: float
    wind_u_ms: float | None
    wind_v_ms: float | None
    current_speed_knots: float
    current_direction_deg: float
    wind_speed_ms: float | None
    wind_direction_deg: float | None
    current_source: str
    weather_source: str
    is_fallback: bool
```

기존 `WeatherData`, `CurrentData`를 유지해도 되지만 OpenDrift reader에 전달할 수 있도록 u/v 성분 변환 함수를 제공한다.

### 5.2 데이터 소스 우선순위

1. CMEMS 격자 해류 데이터
2. KHOA 인접 관측소 또는 예보 데이터
3. 설정된 fallback 데이터

기상 데이터는 KMA를 우선 사용한다.

### 5.3 환경 변수

```env
DATA_GO_KR_API_KEY=
CMEMS_USERNAME=
CMEMS_PASSWORD=
CMEMS_DATASET_ID=
DRIFT_USE_MOCK_ENV=false
DRIFT_MODEL_PATH=/app/engine/artifacts/l3_correction.joblib
DRIFT_MODEL_METADATA_PATH=/app/engine/artifacts/model_metadata.json
DRIFT_DEFAULT_PARTICLE_COUNT=1000
DRIFT_RANDOM_SEED=42
```

응답에는 실제 사용한 소스를 다음 필드에 기록한다.

- `current_data_source`
- `weather_data_source`
- `data_freshness_ok`

---

## 6. L1 물리 모델

### 6.1 역할

- 조류 벡터와 풍압(leeway) 벡터 결합
- 선박/표류체 유형별 leeway 계수 적용
- 결정론적 표류 방향, 속도, 중심점 계산

### 6.2 입력

- 마지막 위치와 시각
- `VesselType`
- 톤수
- 예측 시간
- 조류 속도/방향
- 풍속/풍향

### 6.3 출력

```python
@dataclass
class L1Result:
    direction_deg: float
    speed_knots: float
    predicted_lon: float
    predicted_lat: float
    leeway_coefficient: float
```

위경도 이동 계산은 작은 거리 근사 또는 `pyproj.Geod`를 사용한다. 해상 거리 계산을 도 단위 단순 합산으로 처리하지 않는다.

---

## 7. L2 OpenDrift 및 Monte Carlo

### 7.1 역할

- 입자 초기 위치, 환경장, 불확실성을 구성한다.
- 시간별 입자 위치를 계산한다.
- 입자 분포의 중심, 확산도 및 수색 확률 구역 생성에 필요한 원자료를 반환한다.

### 7.2 내부 인터페이스

```python
def run_drift_prediction(
    request: PredictionRequest,
    environment: EnvironmentData,
    particle_count: int,
) -> DriftSimulationResult:
    ...
```

```python
@dataclass
class ParticleSnapshot:
    hours: int
    lon: np.ndarray
    lat: np.ndarray
    status: np.ndarray

@dataclass
class DriftSimulationResult:
    snapshots: list[ParticleSnapshot]
    particle_count: int
```

### 7.3 구현 조건

- 기본 입자 수는 1,000개로 하며 환경 변수로 조정할 수 있다.
- 요청의 `simulation_hours`에 대해 1시간 단위 snapshot을 만든다.
- `object_type`을 새로 만들지 않고 기존 `VesselType`을 OpenDrift 설정으로 매핑한다.
- 재현 가능한 테스트를 위해 random seed를 주입할 수 있어야 한다.
- OpenDrift 객체는 API view가 아니라 runner 내부에서 생성하고 종료한다.
- OpenDrift import가 실패한 경우 real 엔진 초기화 단계에서 명확한 설정 오류를 발생시킨다.

### 7.4 실패 정책

- 데이터 소스 실패: fallback 환경 데이터 사용 가능
- ML 모델 실패: L3 비활성화 후 L1+L2 사용 가능
- OpenDrift 실행 실패: `DriftSimulationError` 발생
- 빈 입자 결과 또는 전 입자 invalid: 성공 응답을 만들지 않는다.

---

## 8. L3 LightGBM 위치 오차 보정

### 8.1 모델 목적

LightGBM은 OpenDrift를 대체하지 않는다. L1/L2 예측 중심과 실제 발견 위치 사이의 잔차를 예측한다.

권장 target은 위경도 degree가 아니라 지역 좌표계의 거리다.

```text
target_east_m  = actual_east_m  - predicted_east_m
target_north_m = actual_north_m - predicted_north_m
```

모델은 다음 두 개의 regressor로 구성한다.

- `east_model`: 동서 방향 잔차(m)
- `north_model`: 남북 방향 잔차(m)

추론 후 잔차를 위경도로 변환해 다음 계약 필드에 기록한다.

- `l3_delta_lon`
- `l3_delta_lat`

### 8.2 기본 feature

```text
start_lat
start_lon
prediction_hours
vessel_type
tonnage_tons
current_speed_knots
current_dir_sin
current_dir_cos
wind_speed_ms
wind_dir_sin
wind_dir_cos
leeway_coefficient
l1_speed_knots
l1_dir_sin
l1_dir_cos
l2_center_lat
l2_center_lon
l2_spread_km
particle_count
month_sin
month_cos
hour_sin
hour_cos
```

방향, 월, 시간처럼 순환하는 값은 sin/cos로 변환한다. 문자열 category의 encoding 방식은 metadata에 기록한다.

### 8.3 적용 조건

다음 조건을 모두 만족할 때만 L3를 적용한다.

- 모델 파일과 metadata가 존재한다.
- metadata의 feature schema가 런타임 schema와 일치한다.
- 전체 학습 건수가 최소 기준 이상이다.
- 현재 조건과 유사한 학습 사례가 30건 이상이다.
- 예측 결과가 metadata에 기록된 허용 범위를 벗어나지 않는다.

적용하지 않는 경우:

```text
l3_correction_applied = false
l3_delta_lat = 0.0
l3_delta_lon = 0.0
weight_l3 = 0.0
```

### 8.4 가중치

기본값은 기존 계약을 따른다.

```text
L1 = 0.30
L2 = 0.50
L3 = 0.20
```

L3 미적용 시 가중치는 합이 1이 되도록 재정규화한다.

```text
L1 = 0.375
L2 = 0.625
L3 = 0.0
```

현재 contract는 각 weight 합을 검증하지 않으므로 엔진 단위 테스트에서 합이 1인지 검증한다.

---

## 9. 수색 구역 생성

### 9.1 출력 형식

현재 프론트엔드와 계약에 맞춰 최종 결과는 세 개의 누적 확률 폴리곤을 반환한다.

```text
priority 1: 60%
priority 2: 80%
priority 3: 95%
```

각 feature의 properties는 다음 필드를 포함한다.

```json
{
  "priority": 1,
  "cumulative_probability": 0.60,
  "area_km2": 32.2,
  "center_lon": 124.461,
  "center_lat": 38.021,
  "radius_km": 3.2
}
```

### 9.2 계산 방식

MVP 권장 방식:

1. 입자를 지역 투영 좌표계로 변환한다.
2. KDE 또는 weighted density grid를 계산한다.
3. 밀도 내림차순으로 누적 확률 60/80/95% threshold를 구한다.
4. threshold contour를 polygon으로 변환한다.
5. geometry를 정리한 뒤 WGS84 GeoJSON으로 변환한다.

단순 타원은 OpenDrift 결과를 사용할 수 없는 mock/fallback 구현에서만 허용한다.

### 9.3 시간별 결과

각 1시간 snapshot마다 `TimeStepResult`를 생성한다.

```python
TimeStepResult(
    hours=hour,
    search_zones=feature_collection,
    predicted_center=Coordinate(...),
    drift_distance_nm=...,
)
```

최종 `predicted_center`와 `search_zones`는 마지막 time step과 일치해야 한다.

### 9.4 particle/heatmap 공개 범위

현재 `EnginePredictionResult`에는 raw particle과 heatmap 필드가 없다. 첫 구현에서는 API에 추가하지 않는다.

필요해질 경우 기존 필드를 임의로 끼워 넣지 말고 다음 절차를 따른다.

1. `contracts.models`에 optional 필드 추가
2. JSON Schema와 OpenAPI 재생성
3. frontend type 재생성
4. mock/real 엔진 contract test 추가

---

## 10. 학습 데이터

### 10.1 실제 데이터 권장 schema

```text
incident_id
last_seen_at
start_lat
start_lon
vessel_type
tonnage_tons
prediction_hours
current_speed_knots
current_direction_deg
wind_speed_ms
wind_direction_deg
l1_center_lat
l1_center_lon
l2_center_lat
l2_center_lon
l2_spread_km
particle_count
found_at
actual_lat
actual_lon
target_east_m
target_north_m
```

### 10.2 synthetic 데이터

실제 사고 데이터가 부족할 때 synthetic 데이터로 파이프라인을 검증할 수 있다. 다만 synthetic 모델의 예측을 실제 구조 성능으로 표현해서는 안 된다.

생성 절차:

1. 한국 근해에서 시작 위치와 계절을 샘플링한다.
2. 기준 환경장으로 OpenDrift reference trajectory를 생성한다.
3. 시작 위치, 시각, 해류, 풍속에 관측 오차를 추가한다.
4. noisy trajectory를 다시 생성한다.
5. reference와 noisy endpoint의 동서/남북 차이를 target으로 저장한다.

### 10.3 데이터 분할

무작위 행 분할만 사용하지 않는다. 동일 사고 또는 인접 시공간 데이터가 train/test에 동시에 들어가면 leakage가 발생한다.

권장 분할:

- 사건 단위 group split
- 시간 순서 기반 holdout
- 해역별 holdout 성능 추가 보고

---

## 11. 학습 및 모델 메타데이터

### 11.1 학습 스크립트

```powershell
python engine/scripts/train_l3_model.py `
  --input data/incidents.parquet `
  --output engine/artifacts/l3_correction.joblib `
  --metadata engine/artifacts/model_metadata.json
```

LightGBM을 사용할 수 없는 개발 환경에서는 RandomForest를 호환 fallback으로 사용할 수 있지만, metadata의 `model_type`에 반드시 기록한다.

### 11.2 metadata 예시

```json
{
  "model_version": "l3-0.1.0",
  "model_type": "LightGBMRegressorPair",
  "targets": ["target_east_m", "target_north_m"],
  "features": ["start_lat", "start_lon", "prediction_hours"],
  "training_records": 1200,
  "created_at": "2026-06-12T00:00:00+09:00",
  "metrics": {
    "endpoint_mae_km": 1.8,
    "endpoint_p90_km": 4.6
  },
  "training_data_version": "incidents-2026-05"
}
```

pickle/joblib 파일은 신뢰된 배포 artifact만 로드한다. 사용자 업로드 모델을 직접 역직렬화하지 않는다.

---

## 12. 위험 예측 모듈과의 관계

위험 예측 구현은 L3 모델 객체를 직접 import하지 않는다. 위치 보정 모델과 사고 위험 점수 모델은 target이 다르기 때문이다.

초기 구현에서는 다음처럼 분리한다.

- `engine`: 특정 사고의 표류 위치 및 수색 구역 예측
- `risk`: 특정 해역/시간의 사고 위험도 예측

공유 가능한 것은 feature 변환 함수와 환경 데이터 adapter까지다. 동일 LightGBM artifact를 억지로 재사용하지 않는다.

---

## 13. 백엔드 연결

### 13.1 설정 변경

`backend/apps/sar/engine_interface.py`는 다음 의미를 갖도록 수정한다.

```python
if settings.DRIFT_ENGINE == "mock":
    return MockEngine()
if settings.DRIFT_ENGINE == "real":
    return RealDriftEngine()
raise ImproperlyConfigured(...)
```

real을 요청했는데 패키지가 없을 때 조용히 mock으로 전환하지 않는다. 운영에서 mock 결과를 실제 결과로 오인할 수 있기 때문이다.

### 13.2 동기/비동기 실행

MVP에서는 현재 API와 동일하게 동기 호출할 수 있다. OpenDrift 실행 시간이 HTTP timeout을 초과하면 Celery 작업으로 전환한다.

Celery 전환 시 API 상태:

- 생성 요청: `202 Accepted`
- 조회 중: `202 Accepted`
- 완료: `200 OK`
- 실패: 명시적인 실패 상태와 오류 코드

현재 동기 API를 비동기로 바꾸는 작업은 별도 contract 변경으로 취급한다.

---

## 14. 오류 분류

```text
INVALID_INPUT
ENVIRONMENT_DATA_FAILED
OPENDRIFT_NOT_AVAILABLE
OPENDRIFT_FAILED
MODEL_SCHEMA_MISMATCH
MODEL_PREDICTION_FAILED
EMPTY_PARTICLE_RESULT
INTERNAL_ERROR
```

ML 실패는 L3 fallback이 가능하지만 로그와 결과 metadata에 남겨야 한다. OpenDrift 실패는 임의의 mock 결과로 대체하지 않는다.

API 응답에서 내부 stack trace, API key, 로컬 파일 경로는 노출하지 않는다.

---

## 15. 테스트 기준

### 15.1 단위 테스트

- 벡터 합성 방향과 속도
- 위경도/지역 좌표 변환 왕복 오차
- 동일 seed의 재현성
- L3 모델 없음/metadata 불일치 fallback
- weight 합 1.0
- 수색 구역의 유효한 GeoJSON
- 60/80/95% polygon 면적의 단조 증가
- 시간에 따른 표류 거리 증가

### 15.2 contract 테스트

실제 엔진 결과를 다음 두 방식으로 검증한다.

```python
EnginePredictionResult.model_validate(result.model_dump())
```

```python
jsonschema.validate(result.model_dump(mode="json"), generated_schema)
```

### 15.3 통합 테스트

- `DRIFT_ENGINE=mock` 기존 테스트 유지
- `DRIFT_ENGINE=real`, mock 환경 데이터, 작은 입자 수로 API 테스트
- 외부 API 호출 없이 CI에서 실행 가능해야 함
- 실제 CMEMS/KHOA 연동 테스트는 별도 marker로 분리

### 15.4 모델 평가 기준

최소 보고 지표:

- endpoint MAE(km)
- endpoint median error(km)
- endpoint p90 error(km)
- L1/L2 baseline 대비 개선율
- 선박 유형별 MAE
- 해역별 MAE
- 예측 시간 구간별 MAE

synthetic test 성능과 실제 incident holdout 성능을 구분해 기록한다.

---

## 16. 구현 단계

### Phase 1: 엔진 골격

- `engine/pyproject.toml` 작성
- `RealDriftEngine` 공개 인터페이스 구현
- mock 환경 데이터로 contract-valid 응답 생성
- backend의 `DRIFT_ENGINE=real` 연결

### Phase 2: L1 물리 모델

- leeway mapping 이전
- 벡터 및 위치 이동 계산 구현
- 단위 테스트 작성

### Phase 3: L2 OpenDrift

- runner와 reader adapter 구현
- 시간별 입자 snapshot 생성
- CI용 deterministic simplified reader 제공

### Phase 4: 수색 구역

- KDE/density contour 구현
- 60/80/95% GeoJSON 생성
- time step 결과 연결

### Phase 5: L3 fallback

- feature pipeline 구현
- 모델 loader와 schema 검증
- 모델이 없을 때 L1+L2 재정규화

### Phase 6: 학습 파이프라인

- synthetic dataset generator
- LightGBM pair 학습
- 평가 및 metadata 생성

### Phase 7: 실제 데이터 검증

- 사고 이력 정제
- 사건/시간 기반 holdout
- baseline 비교
- 운영 threshold 확정

### Phase 8: 운영화

- 모델 artifact 공급 방식 확정
- 엔진 버전 및 모델 버전 로깅
- 장시간 실행 시 Celery 전환
- 모니터링 및 fallback 비율 수집

---

## 17. 완료 기준

다음 조건을 모두 만족하면 1차 모델 엔진 구현이 완료된 것으로 본다.

1. `RealDriftEngine.predict()`가 `PredictionRequest`를 받아 `EnginePredictionResult`를 반환한다.
2. 모든 시간 단계에 유효한 중심점과 3개 수색 구역이 존재한다.
3. 모델 파일이 없어도 L1+L2 결과가 정상 반환된다.
4. L3 적용 여부와 보정량이 응답에 정확히 기록된다.
5. `DRIFT_ENGINE=real`에서 Django prediction API가 동작한다.
6. 외부 API 없이 real 엔진 통합 테스트를 실행할 수 있다.
7. contract 및 JSON Schema 테스트를 통과한다.
8. 모델 평가는 L1/L2 baseline과 비교해 보고된다.

---

## 18. 구현 시 금지 사항

- 별도 FastAPI 서버를 추가하지 않는다.
- `contracts`와 중복되는 schema를 만들지 않는다.
- LightGBM을 물리 모델의 대체물로 사용하지 않는다.
- 모델 또는 OpenDrift 실패를 무조건 mock 성공 결과로 숨기지 않는다.
- synthetic 데이터 성능을 실제 사고 성능으로 표현하지 않는다.
- raw pickle/joblib 파일을 Git에 커밋하지 않는다.
- `risk` 모델과 위치 오차 보정 모델을 target 검증 없이 공유하지 않는다.
