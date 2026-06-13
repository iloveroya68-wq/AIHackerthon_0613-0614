# DRIFT · engine/

표류 예측 엔진 패키지 (L1 + L2 + L3).

## 역할

`contracts.PredictionRequest` 를 받아 `contracts.EnginePredictionResult` 를 반환하는 단일 함수를 공개한다.

```python
# 유일한 공개 인터페이스
from drift_engine import predict

result: EnginePredictionResult = predict(request)
```

## 브랜치

`feature/model`

## 레이어 구조

| 레이어 | 역할 | 구현 |
|--------|------|------|
| L1 | 물리 표류 벡터 (IAMSAR) | `drift_engine/l1_physics.py` |
| L2 | Monte Carlo 1,000입자 시뮬레이션 | `drift_engine/l2_monte_carlo.py` |
| L3 | LightGBM 오차 보정 | `drift_engine/l3_correction.py` |
| fusion | 가중 합산 (0.30·L1 + 0.50·L2 + 0.20·L3) | `drift_engine/fusion.py` |

## 외부 의존

- 조류 데이터: KHOA 조류예보 API (또는 CSV fallback)
- 기상 데이터: KMA 해양기상 API (또는 CSV fallback)

## 입출력

```
Input : contracts.PredictionRequest
Output: contracts.EnginePredictionResult
```

backend 코드를 import 하지 않는다. `contracts` 만 의존한다.

## Fallback 규칙

학습 데이터 < 30건이면 L3 가중치를 자동으로 0으로 설정하고 L1+L2만 사용한다.

## 현재 구현 실행

기본 real 엔진은 재현 가능한
synthetic L2를 사용한다.

```env
DRIFT_ENGINE=real
DRIFT_L2_ENGINE=synthetic
ENGINE_PARTICLE_COUNT=1000
```

OpenDrift가 설치된 환경에서는 다음과 같이 전환한다.

```env
DRIFT_ENGINE=real
DRIFT_L2_ENGINE=opendrift
```

Bundled historical CMEMS/KHOA data can be selected independently of the L2 engine:

```env
DRIFT_DATA_SOURCE=historical
DRIFT_DATA_ROOT=/data/modeling_inputs
DRIFT_DATA_HOST_PATH=./data/modeling_inputs
```

The historical adapter reads CMEMS currents, KHOA weather, leeway coefficients, and the
land mask through replaceable provider classes in `drift_engine/data_sources/`.

기능 시연용 LightGBM 모델 생성 및 전체 파이프라인 확인:

```powershell
docker compose -f docker-compose.test.yml run --rm demo-train
docker compose -f docker-compose.test.yml run --rm demo-smoke
```

첫 명령은 합성 데이터 2,000건으로 모델을 학습해 `engine/artifacts/`에 저장합니다.
두 번째 명령은 실제 CMEMS/KHOA 데이터, OpenDrift, LightGBM L3를 함께 실행합니다.

OpenDrift 1.14.x는 NumPy 1.26 기반 conda 환경을 권장한다. 모델 파일이 없거나
metadata가 맞지 않으면 L3는 비활성화되고 L1+L2 가중치가 재정규화된다.

Synthetic 데이터 및 LightGBM artifact 생성:

```powershell
python engine/scripts/generate_synthetic_dataset.py --output data/l3_synthetic.csv
python engine/scripts/train_l3_model.py `
  --input data/l3_synthetic.csv `
  --output engine/artifacts/l3_correction.joblib `
  --metadata engine/artifacts/model_metadata.json
```

Synthetic 모델은 파이프라인 검증용이며 실제 사고 성능 지표로 사용하지 않는다.

## Docker 테스트

Docker Desktop이 실행된 상태에서 저장소 루트에서 실행한다.

```powershell
# Django API + synthetic L2 + 엔진 계약 테스트
docker compose -f docker-compose.test.yml run --rm test

# 실제 OpenDrift Leeway 100입자 smoke test
docker compose -f docker-compose.test.yml run --rm test-opendrift

# synthetic CSV 생성 + LightGBM 학습 artifact 생성 smoke test
docker compose -f docker-compose.test.yml run --rm train-smoke
```

최초 실행은 OpenDrift 의존성 이미지 빌드 때문에 시간이 걸릴 수 있다. 이후 실행은
Docker layer cache를 사용한다.
