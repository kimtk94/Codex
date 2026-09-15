# Kalman Multi-Market Phase 1 Collector

서버/cron에서 바로 실행할 수 있는 read-only 데이터 수집기입니다.

## 1. 이번 버전의 범위

### US
- SPY
- QQQ
- SOXX
- US 2Y (FRED: DGS2)
- US 10Y (FRED: DGS10)

### KR
- KOSPI (`FinanceDataReader: KS11`)
- KOSDAQ (`FinanceDataReader: KQ11`)
- KR 3Y / 10Y
  - ECOS mapping 설정 시 ECOS 우선
  - 설정이 없으면 FinanceDataReader fallback
- USD/KRW
  - ECOS mapping 설정 시 ECOS 우선
  - 설정이 없으면 FinanceDataReader fallback

### BTC
- Upbit `KRW-BTC` daily OHLCV

## 2. 기존 Investment Hub에서 유지한 규칙

1. **부분봉을 모델 입력에 넣지 않음**
2. `event_time`과 `available_time`을 분리
3. FRED 계열은 기본 `+2 day`, KR macro는 기본 `+1 day`
4. derived feature의 `available_time`은 input 중 가장 늦은 시각
5. secret 값은 출력/Drive에 저장하지 않고 presence만 보고
6. 한 source 실패가 전체 job을 죽이지 않는 source-level fail-soft
7. raw / feature / eligible-feature를 분리 저장

## 3. 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env`에 최소 다음을 입력합니다.

```env
ALPACA_API_KEY_ID=...
ALPACA_API_SECRET_KEY=...
FRED_API_KEY=...
```

ECOS는 선택입니다. ECOS series/item code를 확정하기 전에는 FinanceDataReader fallback으로 KR 지표를 받을 수 있습니다.

## 4. 설정 검증

외부 API 호출 없이 secret 존재 여부와 mapping 상태만 확인:

```bash
python multimarket_phase1.py --dry-run
```

## 5. 실행

```bash
python multimarket_phase1.py
```

생성물:

```text
data/
├── raw/
│   ├── phase1_raw.csv
│   └── phase1_raw.parquet
├── features/
│   ├── phase1_features.csv
│   ├── phase1_features.parquet
│   ├── phase1_features_eligible.csv
│   └── phase1_features_eligible.parquet
├── snapshots/
│   ├── phase1_latest.csv
│   └── phase1_latest.parquet
└── run_summary.json
```

## 6. 주요 feature

가격계열:
- RET_1D / 5D / 20D
- MA20 distance
- RV20
- Z60

금리계열:
- CHG_1D / 5D
- Z60

Cross-asset:
- QQQ / SPY
- SOXX / QQQ
- KOSDAQ / KOSPI
- ratio level / 5D return / Z60

## 7. cron 예시

한국시간 매일 오전 08:10:

```cron
CRON_TZ=Asia/Seoul
10 8 * * * cd /opt/kalman && /opt/kalman/.venv/bin/python multimarket_phase1.py >> logs/phase1.log 2>&1
```

한국 장 마감 후 별도 갱신이 필요하면 16:10 job을 추가할 수 있습니다.

```cron
CRON_TZ=Asia/Seoul
10 16 * * 1-5 cd /opt/kalman && /opt/kalman/.venv/bin/python multimarket_phase1.py >> logs/phase1.log 2>&1
```

## 8. 다음 단계

이 collector 다음에 붙일 권장 구조:

```text
collector
  -> raw parquet
  -> leakage-safe feature build
  -> daily model matrix
  -> US model
  -> KR model
  -> BTC model
  -> Meta / Global Regime model
  -> evidence registry
```

실매매 연결은 이 단계와 분리합니다.
