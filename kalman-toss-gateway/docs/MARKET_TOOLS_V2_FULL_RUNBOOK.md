# Kalman Market Tools V2 — Full Stack Runbook

> 범위: Provider → Point-in-Time Screener → TA-Lib V2 → vectorbt Research
>
> 상태: production execution과 분리된 shadow/research stack
>
> 실거래 승격은 이 문서의 범위가 아니다.

---

## 1. 전체 구조

```text
                     KALMAN MARKET TOOLS V2

 yfinance ──────┐
 FDR ───────────┼──> Canonical Market Data ──> raw snapshots
 pykrx ─────────┘              |
                               +──> provider comparison
                               |
                               v
                         TA-Lib V2 Features
                               |
                               v
                       versioned feature set

 Finviz ──> point-in-time dated snapshots ──> candidate universe

 saved price + saved features
              |
              v
       fixed research dataset
              |
              v
     vectorbt isolated venv
        |             |
        v             v
    backtest      walk-forward

No component above writes strategy_signal or submits Toss orders.
```

---

## 2. Python 환경

세 환경을 섞지 않는다.

### Production

```text
/opt/kalman/.venv
```

용도:

- Unified model
- Neon
- Toss gateway
- auto_trade

### Market Tools V2

```text
/opt/kalman/.venv-market-v2
```

용도:

- yfinance
- pykrx
- FinanceDataReader
- finvizfinance
- TA-Lib

### Research V2

```text
/opt/kalman/.venv-research-v2
```

용도:

- vectorbt 1.1.0
- pandas 3 계열
- research/report

vectorbt 1.1.0은 현재 pandas 3.0.3 이상과 NumPy 2.4.6 이상을 요구하므로 Market V2 환경과 분리한다.

---

## 3. 서버 배포

Repository update 후:

```bash
cd ~/Codex
git pull
cd kalman-toss-gateway
sudo bash scripts/install_server.sh
```

`install_server.sh`는 production requirements만 production venv에 설치한다.

`research/` 코드는 서버에 복사하지만 research dependency는 설치하지 않는다.

---

## 4. V2 환경 설치

### Market V2

```bash
sudo /opt/kalman/app/scripts/install_market_tools_v2.sh
```

### vectorbt Research

```bash
sudo /opt/kalman/app/scripts/install_market_research_v2.sh
```

확인:

```bash
/opt/kalman/.venv-market-v2/bin/python - <<'PY'
import FinanceDataReader
import finvizfinance
import talib
import yfinance
from pykrx import stock
print("market-v2: OK")
PY

/opt/kalman/.venv-research-v2/bin/python - <<'PY'
import vectorbt
print("vectorbt", vectorbt.__version__)
PY
```

---

## 5. Market Data 수집

```bash
sudo /opt/kalman/app/scripts/run_market_data_v2.sh
```

기본 provider map:

| Logical asset | Provider |
|---|---|
| SPY | yfinance SPY |
| BTC-USD | yfinance BTC-USD + FDR BTC/USD |
| USD/KRW | yfinance KRW=X + FDR USD/KRW |
| KOSPI | yfinance ^KS11 + FDR KS11 + pykrx 1001 |

기본 output:

```text
/mnt/gdrive/Market_Data/v2/
├── raw/
│   ├── yfinance/
│   ├── financedatareader/
│   └── pykrx/
├── validation/provider_comparison.json
└── market_data_v2_run_status.json
```

---

## 6. Provider 비교

확인:

```bash
cat /mnt/gdrive/Market_Data/v2/validation/provider_comparison.json
```

현재 비교:

- BTC: yfinance vs FDR
- USD/KRW: yfinance vs FDR
- KOSPI: yfinance vs FDR
- KOSPI: pykrx vs FDR

현재는 차이 threshold가 투자 로직에 연결되지 않는다.

목적은 source anomaly 관찰과 기준값 설정이다.

---

## 7. Finviz Point-in-Time Screener

### 기본 상태

```env
KALMAN_FINVIZ_ENABLED=false
```

Finviz는 scraping 기반이므로 core price source가 아니다.

Cloudflare/HTML 변경/403이 발생해도 production pipeline에는 영향이 없어야 한다.

### 최초 manual test

```bash
sudo /opt/kalman/app/scripts/run_finviz_v2.sh --force --limit 100
```

성공 후에만:

```env
KALMAN_FINVIZ_ENABLED=true
```

로 변경한다.

### Filter

예:

```env
KALMAN_FINVIZ_FILTERS_JSON={"Index":"S&P 500"}
```

실제 filter 이름과 option은 finvizfinance에서 지원하는 값만 사용한다.

### Local filter

```env
KALMAN_FINVIZ_MIN_PRICE=5
KALMAN_FINVIZ_MIN_MARKET_CAP=1000000000
KALMAN_FINVIZ_MIN_VOLUME=500000
```

0은 해당 local filter를 비활성화한다.

### 저장

```text
/mnt/gdrive/Market_Screeners/finviz/
├── finviz_run_status.json
└── YYYY-MM-DD/
    ├── overview.parquet
    ├── valuation.parquet
    ├── financial.parquet
    ├── performance.parquet
    ├── technical.parquet
    ├── merged_snapshot.parquet
    └── candidate_universe.parquet
```

오늘 받은 snapshot을 과거 날짜에 backfill하지 않는다.

---

## 8. TA-Lib V2

실행:

```bash
sudo /opt/kalman/app/scripts/run_features_v2.sh
```

output:

```text
/mnt/gdrive/Market_Features/v2/
├── feature_registry.json
├── features_v2_run_status.json
└── talib/
    ├── spy.parquet
    ├── btc_usd.parquet
    └── kospi.parquet
```

현재 V2 feature:

- RSI14
- MACD
- MACD signal
- MACD histogram
- ADX14
- ATR14
- NATR14
- ROC10
- OBV
- Bollinger upper/mid/lower
- Bollinger %B

기존 production RSI는 변경하지 않는다.

---

## 9. Legacy RSI parity report

각 asset metadata 안에 다음이 기록된다.

- mean absolute difference
- max absolute difference
- mean signed difference
- correlation
- RSI 30/70 zone disagreement
- first valid index

목적은 TA-Lib 계산을 기존 모델에 몰래 치환하지 않고 차이를 정량화하는 것이다.

---

## 10. 전체 Shadow 수집

```bash
sudo /opt/kalman/app/scripts/run_market_tools_v2.sh
```

순서:

```text
Market Data
 -> TA-Lib Features
 -> Finviz
```

Finviz가 disabled이면 status만 DISABLED로 남고 나머지 layer는 정상 동작한다.

---

## 11. vectorbt Research

먼저 Market Data와 TA-Lib feature가 있어야 한다.

### SPY

```bash
sudo /opt/kalman/app/scripts/run_research_v2.sh SPY
```

### BTC

```bash
sudo /opt/kalman/app/scripts/run_research_v2.sh BTC-USD
```

### KOSPI

```bash
sudo /opt/kalman/app/scripts/run_research_v2.sh KOSPI
```

---

## 12. Research output

```text
/mnt/gdrive/Market_Research/v2/
├── datasets/
│   ├── spy.parquet
│   ├── btc_usd.parquet
│   └── kospi.parquet
└── reports/
    ├── spy_backtest.json
    ├── spy_walk_forward.json
    ├── btc_usd_backtest.json
    ├── btc_usd_walk_forward.json
    ├── kospi_backtest.json
    └── kospi_walk_forward.json
```

backtest 시 인터넷에서 price를 다시 받지 않는다.

저장된 Kalman snapshot만 사용한다.

---

## 13. 기본 RSI strategy의 의미

`research/market_tools/configs/rsi_threshold_v1.json`은 production 전략이 아니다.

현재 목적:

- vectorbt API 검증
- saved dataset 재현성 검증
- fees/slippage 반영 확인
- report pipeline 확인
- walk-forward 동작 확인

기본:

```text
entry: RSI > 55
exit : RSI < 45
fees : 0.1%
slippage: 0.05%
```

성과가 좋더라도 바로 실거래로 승격하지 않는다.

---

## 14. Walk-forward

기본:

```text
train: 504 observations
test : 126 observations

entry grid: 50 / 55 / 60
exit grid : 40 / 45 / 50
```

각 train window에서 Sharpe가 가장 높은 threshold를 고른 뒤 다음 test window에 적용한다.

이는 V2 research harness이며 최종 모델 selection 방법은 별도로 설계한다.

---

## 15. Cron

현재 실제 cron에는 등록하지 않는다.

Template:

```text
config/market-tools-v2.cron.example
```

Manual validation 완료 후에만 enable 여부를 결정한다.

Research/vectorbt job은 기본적으로 cron에 넣지 않는다.

---

## 16. GitHub Actions

`.github/workflows/kalman-market-data-v2.yml`은 두 환경을 따로 검증한다.

### market-v2 job

- FDR
- finvizfinance
- TA-Lib
- Python compile
- shell syntax
- offline unit tests

### research-v2 job

- vectorbt isolated dependency
- research compile
- vectorbt API smoke

CI가 통과해도 Finviz 실제 network access나 서버 GDrive mount까지 증명하는 것은 아니다.

---

## 17. Production boundary

다음 파일/경로는 이 stack이 수정하지 않는다.

```text
engine/unified_runner.py
engine/_unified_payload_*.b64
engine/pipeline_entry.py
engine/auto_trade.py
engine/position_manager.py
app/executor.py
app/toss_client.py
Neon strategy_signal
```

---

## 18. Failure behavior

### Market data required source failure

V2 runner FAIL.

production unaffected.

### FDR/pykrx optional source failure

V2 DEGRADED.

production unaffected.

### Finviz failure

Finviz FAIL.

Market Data / TA-Lib / production unaffected.

### TA-Lib failure

feature V2 FAIL.

legacy feature pipeline unaffected.

### vectorbt failure

research FAIL.

production unaffected.

---

## 19. 서버 최초 검증 순서

아래 순서대로 확인한다.

```bash
# 1. 기존 production
sudo /opt/kalman/app/scripts/preflight.sh
sudo /opt/kalman/app/scripts/smoke_test.sh --pipelines

# 2. V2 deps
sudo /opt/kalman/app/scripts/install_market_tools_v2.sh
sudo /opt/kalman/app/scripts/install_market_research_v2.sh

# 3. Market data
sudo /opt/kalman/app/scripts/run_market_data_v2.sh --start-date 2024-01-01

# 4. TA-Lib
sudo /opt/kalman/app/scripts/run_features_v2.sh

# 5. Finviz manual
sudo /opt/kalman/app/scripts/run_finviz_v2.sh --force --limit 100

# 6. Research
sudo /opt/kalman/app/scripts/run_research_v2.sh SPY
sudo /opt/kalman/app/scripts/run_research_v2.sh BTC-USD
sudo /opt/kalman/app/scripts/run_research_v2.sh KOSPI

# 7. 기존 production 재검증
sudo /opt/kalman/app/scripts/smoke_test.sh --pipelines
```

---

## 20. 승격 금지 조건

아래 중 하나라도 해당하면 production model에 연결하지 않는다.

- provider mismatch 원인 미확인
- Finviz point-in-time archive 부족
- TA-Lib legacy parity 미검토
- leakage 검사 미완료
- walk-forward 미완료
- transaction cost sensitivity 미완료
- SHADOW signal 비교 미완료

---

## 21. 다음 단계

이 full stack 이후의 다음 단계는 library 추가가 아니다.

다음은:

```text
US / KR / BTC / Common V2 Feature Matrix
        ↓
Feature Selection
        ↓
Model candidate
        ↓
Out-of-sample / Walk-forward
        ↓
Neon SHADOW strategy_version
```

이다.

OpenBB와 Freqtrade는 현재 full stack의 필수 dependency가 아니다.
