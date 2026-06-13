# DRIFT · contracts/

> **단일 진실 공급원(Single Source of Truth).** 모든 모듈 간 데이터 교환은 이 디렉토리의 계약을 통해서만 이루어집니다.

## 파일 구조

```
contracts/
  __init__.py          # 공개 심볼 export
  models.py            # Pydantic v2 데이터 모델 (비즈니스 로직 없음)
  gen_schemas.py       # JSON Schema 생성 + 예시 검증 스크립트
  openapi.yaml         # REST API 명세 (OpenAPI 3.1)
  schemas/             # gen_schemas.py 가 자동 생성 (커밋 포함)
  examples/            # 각 계약의 mock 예시 JSON
```

## 4개 핵심 계약

| 모델 | 생산자 | 소비자 | 설명 |
|------|--------|--------|------|
| `PredictionRequest` | frontend / operator | backend → engine | 마지막 좌표·시각·선종 입력 |
| `EnginePredictionResult` | engine (L1+L2+L3) | backend | 확률 수색 폴리곤 3순위 |
| `BriefingResult` | backend briefing provider | backend | 4섹션 작전 브리핑 |
| `RiskForecastResult` | risk (P1) | backend | 해역별 DRI Heatmap |

## 계약 변경 규칙

1. **필드 추가** — `Optional` 또는 `default` 필수. 기존 소비자 무중단.
2. **필드 삭제 · 이름 변경** — 반드시 `develop` PR 에서 모든 팀과 사전 합의.
3. **변경 후 필수 실행**:
   ```bash
   cd DRIFT
   pip install pydantic jsonschema
   python contracts/gen_schemas.py --check
   ```
4. `schemas/` 디렉토리는 **커밋 포함**. 자동 생성 파일이지만 diff 검토 필요.

## 지리 데이터 규칙

- 모든 폴리곤/그리드: **GeoJSON FeatureCollection**
- 좌표 순서: **`[longitude, latitude]`** (RFC 7946 표준)
- 예시: `[124.37, 37.96]` → 경도 124.37°E, 위도 37.96°N

## 로컬 실행

```bash
# 스키마 재생성
python contracts/gen_schemas.py

# 스키마 생성 + 예시 검증
python contracts/gen_schemas.py --check
```
