# Kalman Market Tools V2 통합 설계서

> 상태: **Phase 1A 구현 완료 / 서버 실데이터 검증 전**
>
> 목적: Kalman의 현재 production lineage와 Toss 실거래 경로를 보존하면서, 주식 검색·시장 데이터·기술지표·백테스트 기능을 V2 research/shadow layer로 단계적으로 추가한다.
>
> 이 문서는 이후 구현의 기준 문서(source of truth)로 사용한다.

---

## 0. 결론 요약

현재 Kalman은 이미 단순한 투자 대시보드가 아니라 다음 계층을 갖고 있다.

```text
데이터 수집
  -> Unified US/KR/CRYPTO 모델
  -> Neon
  -> strategy_signal
  -> position_manager
  -> auto_trade
  -> Toss Open API
```

따라서 새로운 오픈소스 Tool을 기존 코드에 바로 섞거나, 현재 계산식을 외부 라이브러리로 치환하는 방식은 사용하지 않는다.

Market Tools V2의 기본 원칙은 다음과 같다.

1. **현재 production model과 Toss execution은 그대로 둔다.**
2. **신규 Tool은 V2 shadow/research layer에서 먼저 검증한다.**
3. **동일 이름의 지표라도 기존 feature를 TA-Lib 값으로 덮어쓰지 않는다.**
4. **시장 데이터는 provider abstraction + provenance를 갖도록 표준화한다.**
5. **Finviz와 같은 현재 시점 screener 데이터는 point-in-time snapshot으로 누적한다.**
6. **vectorbt는 production gateway가 아니라 별도 research 환경에서만 사용한다.**
7. **OpenBB는 장기적으로 별도 Data/MCP service로 둔다.**
8. **새 모델은 반드시 새 strategy/model version으로 승격한다.**
9. **기존 R4/R5.1 artifact를 수정하거나 덮어쓰지 않는다.**
10. **실거래 연결은 마지막 단계이며, 기존 fail-closed gate를 그대로 유지한다.**

### 최종 Tool 결정

| Tool | 결정 | 우선순위 | Kalman 역할 |
|---|---|---:|---|
| yfinance | KEEP | P0 | 기존 US/BTC 가격 수집 유지 |
| pykrx | KEEP | P0 | KR 시장 상세 데이터 |
| FinanceDataReader | ADOPT | P1 | KR/US/BTC/FX/FRED 보조 provider + cross-check |
| finvizfinance | ADOPT | P1 | US 종목 screener + candidate universe |
| TA-Lib | ADOPT | P2 | 신규 V2 기술지표 |
| vectorbt | ADOPT | P2 | walk-forward/backtest/parameter validation |
| OpenBB | DEFER | P3 | 별도 Data API/MCP/AI research layer |
| Freqtrade | DEFER | P4 | 향후 crypto exchange-native execution 검토 |
| pandas-ta | SKIP | - | TA-Lib과 기능 중복 |
| backtrader | SKIP | - | vectorbt과 기능 중복 |

---

# 1. 현재 Kalman 구조

## 1.1 Repository 위치

현재 Kalman runtime은 다음 위치에 있다.

```text
kimtk94/Codex/
└── kalman-toss-gateway/
```

주요 구성:

```text
kalman-toss-gateway/
├── app/
│   ├── config.py
│   ├── executor.py
│   ├── main.py
│   ├── managed_positions.py
│   ├── market_guard.py
│   ├── risk.py
│   └── toss_client.py
│
├── engine/
│   ├── unified_runner.py
│   ├── pipeline_entry.py
│   ├── auto_trade.py
│   ├── position_manager.py
│   ├── sa_collector.py
│   └── sa_us_btc_features.py
│
├── scripts/
│   ├── run_pipeline.sh
│   ├── run_auto_trade.sh
│   ├── run_sa_collector.sh
│   ├── run_sa_us_btc_features.sh
│   └── run_sa_us_btc_refresh.sh
│
├── config/
│   ├── kalman.cron
│   └── kalman.cron.d
│
├── docs/
├── requirements.txt
└── .env.example
```

---

## 1.2 현재 production lineage

```text
cron
  -> scripts/run_pipeline.sh
  -> engine.pipeline_entry
  -> engine.unified_runner
  -> frozen Unified US/KR/CRYPTO source/model
  -> Neon PostgreSQL
  -> dashboard_snapshot
  -> strategy_signal
```

Trading은 별도 stateful path다.

```text
strategy_signal
  -> engine.position_manager
  -> engine.auto_trade
  -> app.executor
  -> app.toss_client
  -> Toss Open API
```

### 매우 중요한 경계

**Model pipeline과 Broker execution은 현재 분리되어 있다.**

이 경계를 Market Tools V2에서도 유지한다.

---

# 2. 현재 코드에 이미 존재하는 기능

## 2.1 설치되어 있는 주요 package

현재 `requirements.txt` 기준:

```text
yfinance==1.7.0
pykrx>=1.2.8
pandas>=2.2
numpy>=2.0
scikit-learn==1.6.1
psycopg[binary]>=3.2
exchange-calendars>=4.7
```

특히:

```text
scikit-learn==1.6.1
```

은 frozen R4/R5.1 artifact compatibility 때문에 고정되어 있다.

따라서 production venv에 대규모 신규 dependency를 쉽게 추가해서는 안 된다.

---

## 2.2 이미 구현된 US/BTC feature

`engine/sa_us_btc_features.py`에는 이미 다음이 존재한다.

### Price / Return

- price
- 1-day return
- 5-observation return
- 20-observation return

### Technical / Momentum

- RSI 14
- rolling volatility 20
- rolling z-score 20
- MA20 gap
- MA50 gap
- above MA20
- above MA50

### Breadth

- positive 1d ratio
- above MA20 ratio
- above MA50 ratio
- median 5-observation return
- median 20-observation return
- coverage

### Regime

- HYG/LQD
- QQQ/SPY
- BTC/SPY
- 20-observation return variants

### Seeking Alpha

- Quant Rating
- Momentum
- EPS Revision
- Valuation
- Growth
- Profitability
- Analyst rating
- News sentiment
- BTC ETF factors
- Crypto equity factors

### Composite

- `US_MARKET_COMPOSITE_V1`
- `BTC_MARKET_COMPOSITE_V1`
- `US_SA_COMPOSITE_V1`
- `BTC_SA_EQUITY_COMPOSITE_V1`
- `BTC_SA_ETF_COMPOSITE_V1`

즉 TA-Lib 도입 목적은 **기존 지표 구현 대체가 아니라 신규 후보 feature 확장**이다.

---

# 3. 변경 금지 영역

Market Tools V2 작업 중 아래 항목은 직접 수정하지 않는다.

## 3.1 Frozen model lineage

```text
engine/unified_runner.py
engine/_unified_payload_*.b64
```

현재 Unified source는 LZMA + Base64 chunk로 보관되고 SHA-256 검증 후 실행된다.

현재 artifact는 그대로 둔다.

---

## 3.2 Legacy feature semantics

아래 계산을 TA-Lib/FDR/OpenBB 등의 값으로 자동 치환하지 않는다.

- 기존 RSI
- rolling volatility
- rolling z-score
- MA gap
- breadth
- ratio/regime
- composite
- 현재 model input columns

### 이유

동일한 이름의 지표라도 구현마다 차이가 날 수 있다.

예:

- Wilder smoothing initialization
- EMA initialization
- min_periods
- NaN 처리
- adjusted close 정책
- calendar alignment
- holiday 처리
- forward fill 정책

작은 numerical difference라도 기존 ML artifact inference에 영향을 줄 수 있다.

---

## 3.3 Toss execution contract

아래 경로도 Market Tools V2 Phase 1~4에서는 건드리지 않는다.

```text
engine/auto_trade.py
engine/position_manager.py
app/executor.py
app/toss_client.py
```

신규 screener나 신규 feature가 **직접 주문을 발생시키도록 연결하지 않는다.**

---

# 4. 목표 아키텍처

```text
                         KALMAN MARKET TOOLS V2

      +----------------+   +-------------------+   +---------------+
      | yfinance       |   | FinanceDataReader |   | pykrx         |
      +-------+--------+   +---------+---------+   +-------+-------+
              |                      |                     |
              +----------------------+---------------------+
                                     |
                              Provider Layer
                                     |
                             Canonical Schema
                                     |
                 +-------------------+-------------------+
                 |                                       |
             Market Data                           Macro/Common
                 |                                       |
                 +-------------------+-------------------+
                                     |
                         Point-in-Time Raw Archive
                                     |
                         +-----------+------------+
                         |                        |
                 finviz snapshots          Price/Macro history
                         |                        |
                         +-----------+------------+
                                     |
                            Feature Registry
                         /                    \
             legacy/frozen-compatible       V2
                 기존 계산                TA-Lib
                         \                    /
                          +---------+---------+
                                    |
                           Versioned Dataset
                                    |
                                SHADOW
                                    |
                                vectorbt
                                    |
                    Walk-forward / Cost Validation
                                    |
                         New model candidate
                                    |
                        New strategy_version
                                    |
                             Neon SHADOW
                                    |
                           별도 승격 절차
                                    |
                        기존 Toss execution
```

---

# 5. Provider Layer 설계

## 5.1 목적

각 라이브러리를 모델 코드에서 직접 호출하지 않는다.

잘못된 방식:

```python
import yfinance
import FinanceDataReader
from pykrx import stock

# feature 코드 곳곳에서 직접 호출
```

목표:

```text
Provider
  -> Canonical DataFrame
  -> Validation
  -> Snapshot
  -> Feature
```

---

## 5.2 예정 파일 구조

Phase 1에서 다음 구조를 만든다.

```text
engine/
└── market_data/
    ├── __init__.py
    ├── schema.py
    ├── base.py
    ├── yfinance_provider.py
    ├── fdr_provider.py
    ├── pykrx_provider.py
    ├── validation.py
    └── snapshot.py
```

각 파일 역할:

| 파일 | 역할 |
|---|---|
| `schema.py` | canonical dataframe column 정의 |
| `base.py` | provider 공통 interface |
| `yfinance_provider.py` | 기존 yfinance wrapper |
| `fdr_provider.py` | FinanceDataReader adapter |
| `pykrx_provider.py` | KR market adapter |
| `validation.py` | provider 간 값 비교 |
| `snapshot.py` | atomic save + metadata |

---

# 6. Canonical Schema

## 6.1 OHLCV

표준 컬럼:

```text
timestamp
market
symbol
open
high
low
close
adj_close
volume
currency
source
source_asof
retrieved_at
is_adjusted
```

권장 추가 metadata:

```text
provider_symbol
timezone
frequency
request_start
request_end
```

---

## 6.2 Macro

```text
timestamp
series_id
value
source
source_asof
retrieved_at
frequency
unit
```

---

## 6.3 Screener Snapshot

```text
snapshot_at
ticker
market
sector
industry
market_cap
price
relative_volume
rsi
sma20_relation
sma50_relation
sma200_relation
pe
forward_pe
peg
sales_growth
eps_growth
roe
debt_equity
analyst_field
insider_field
source
retrieved_at
```

필드는 실제 Finviz schema 확인 후 확정한다.

---

# 7. Data Provenance

모든 V2 dataset은 source provenance를 남긴다.

최소 metadata:

```text
provider
retrieved_at
source_asof
symbol/series
row_count
first_timestamp
last_timestamp
missing_count
adjustment_policy
request_parameters
checksum
status
```

예시 metadata:

```json
{
  "provider": "yfinance",
  "symbol": "SPY",
  "retrieved_at": "2026-09-11T21:00:00+09:00",
  "source_asof": "2026-09-10",
  "frequency": "1d",
  "adjusted": false,
  "row_count": 1200,
  "status": "READY"
}
```

---

# 8. FinanceDataReader 도입 범위

## 8.1 도입 이유

FinanceDataReader는 Kalman의 공통 지표에 적합하다.

활용 후보:

### US

- S&P 500
- NASDAQ
- Dow
- Russell 2000
- VIX

### KR

- KOSPI
- KOSDAQ
- KOSPI200

### FX

- USD/KRW
- USD/EUR
- 기타 필요 환율

### Crypto

- BTC/USD
- ETH/USD 필요 시

### Macro

- FRED prefixed series

---

## 8.2 초기 역할

FDR은 Phase 1에서 **primary replacement가 아니다.**

초기 용도:

```text
secondary provider
+
cross-provider validation
+
fallback research source
```

---

## 8.3 비교 대상

예:

| 기준 | Primary | Cross-check |
|---|---|---|
| SPY | yfinance | FDR 가능 범위 |
| BTC/USD | yfinance | FDR |
| KOSPI | pykrx/기존 | FDR |
| USD/KRW | 기존 macro/FRED | FDR |
| VIX | 기존 source | FDR |

---

# 9. Provider Validation

## 9.1 목적

한 provider의 일시적 오류를 모델 변화로 오인하지 않는다.

---

## 9.2 비교 지표

- last close
- 1d return
- 5d return
- missing rows
- trading date alignment
- duplicate dates
- abnormal zero volume
- percent difference

예:

```text
abs(primary_close / secondary_close - 1)
```

---

## 9.3 초기 threshold

초기에는 hard-coded production threshold로 사용하지 않는다.

Shadow validation report에서 분포를 먼저 측정한다.

이후 예를 들어 다음을 정할 수 있다.

```text
WARN:
difference > 0.5%

DEGRADED:
difference > 2%

FAIL:
calendar/source integrity error
```

실제 threshold는 관측 후 확정한다.

---

# 10. finvizfinance 도입 설계

## 10.1 목적

Finviz는 **종목 발견(candidate discovery)** 용도다.

직접 BUY signal generator로 사용하지 않는다.

---

## 10.2 예상 사용

예시 조건:

- Market Cap
- Average Volume
- Relative Volume
- Price
- RSI
- SMA20
- SMA50
- SMA200
- EPS growth
- Sales growth
- ROE
- Debt/Equity
- Sector
- Industry

---

## 10.3 Point-in-Time 원칙

가장 중요하다.

**오늘 가져온 Finviz 값을 과거 날짜에 소급해서 사용하지 않는다.**

잘못된 예:

```text
2026-09-11에 받은 PE/RSI/Analyst data
-> 2025년 training row에 붙임
```

금지.

올바른 방식:

```text
매일 snapshot 저장
-> 해당 날짜 이후에만 사용
```

---

## 10.4 저장 위치

예정:

```text
$KALMAN_DATA_ROOT/
└── Market_Screeners/
    └── finviz/
        ├── 2026-09-11/
        │   ├── raw_snapshot.parquet
        │   ├── candidate_universe.parquet
        │   └── metadata.json
        ├── 2026-09-12/
        └── ...
```

---

## 10.5 Universe 생성

향후 모델 universe는 다음처럼 구성 가능하다.

```text
US base universe
  ∩ liquidity rule
  ∩ market cap rule
  ∩ price rule
  ∩ volatility rule
  ∩ optional Finviz screen
      ↓
candidate universe
```

---

# 11. TA-Lib V2 설계

## 11.1 목적

기존 feature의 대체가 아니다.

**신규 모델 후보 feature 생성**이다.

---

## 11.2 Namespace

모든 신규 feature는 명시적인 version prefix를 사용한다.

예:

```text
talib_v2_rsi14
talib_v2_macd
talib_v2_macd_signal
talib_v2_macd_hist
talib_v2_adx14
talib_v2_atr14
talib_v2_natr14
talib_v2_roc10
talib_v2_obv
talib_v2_bb_upper
talib_v2_bb_mid
talib_v2_bb_lower
talib_v2_bb_pctb
```

---

## 11.3 1차 도입 지표

### Trend

- MACD
- ADX

### Momentum

- RSI
- ROC

### Volatility

- ATR
- NATR
- Bollinger Bands

### Volume

- OBV

처음부터 150개 이상의 indicator를 모두 넣지 않는다.

---

## 11.4 Legacy RSI 비교

반드시 수행:

```text
legacy RSI14
vs
TA-Lib RSI14
```

비교 항목:

- mean absolute difference
- max absolute difference
- correlation
- sign/threshold disagreement
- RSI 30/70 crossing disagreement
- warm-up length

이를 통해 기존 모델 계산과 신규 계산의 차이를 문서화한다.

---

# 12. Feature Registry

V2에서는 feature metadata를 별도로 관리한다.

예정:

```text
research/market_tools/configs/features_v2.yaml
```

개념 예시:

```yaml
feature_set: market_tools_v2_001

features:
  - name: talib_v2_rsi14
    source: ta-lib
    input: close
    lookback: 14
    market: US
    point_in_time: true

  - name: usdkrw_ret20
    source: finance-datareader
    input: USD/KRW
    lookback: 20
    point_in_time: true
```

목표:

- 어떤 feature가
- 어느 source에서
- 어떤 lookback으로
- 어떤 version에서
- 언제 추가되었는지

추적 가능하게 한다.

---

# 13. Dataset Versioning

## 13.1 디렉터리

예정:

```text
$KALMAN_DATA_ROOT/
└── Market_Features/
    └── v2/
        ├── raw/
        ├── canonical/
        ├── features/
        ├── targets/
        ├── manifests/
        └── validation/
```

---

## 13.2 Manifest

각 dataset build는 manifest를 생성한다.

예:

```json
{
  "dataset_version": "market_tools_v2_001",
  "built_at": "...",
  "feature_schema": "...",
  "start": "...",
  "end": "...",
  "providers": {
    "us": "yfinance",
    "kr": "pykrx",
    "secondary": "FinanceDataReader"
  },
  "git_commit": "...",
  "status": "SHADOW"
}
```

---

# 14. vectorbt Research Layer

## 14.1 Production dependency에 넣지 않는 이유

vectorbt는 강력하지만 production Toss gateway가 필요로 하는 runtime dependency가 아니다.

따라서 다음 파일에 넣지 않는다.

```text
kalman-toss-gateway/requirements.txt
```

---

## 14.2 별도 구조

```text
research/
└── market_tools/
    ├── README.md
    ├── requirements.txt
    ├── build_dataset.py
    ├── run_vectorbt.py
    ├── configs/
    │   ├── features_v2.yaml
    │   └── backtest_v1.yaml
    ├── reports/
    └── tests/
```

---

## 14.3 Backtest는 인터넷에서 다시 받지 않는다

재현성을 위해:

잘못된 방식:

```text
vectorbt run
-> yfinance fresh download
-> 결과 생성
```

올바른 방식:

```text
Kalman versioned snapshot
-> vectorbt
-> report
```

즉 backtest input은 고정된 snapshot이어야 한다.

---

# 15. Backtest Validation 기준

최소 검증 항목:

1. Time split
2. Walk-forward
3. No look-ahead
4. No target leakage
5. Data publication lag
6. Entry delay
7. Commission
8. Spread
9. Slippage
10. Market calendar
11. BTC 24/7 calendar
12. Survivorship bias
13. Delisted/security universe consideration
14. Position sizing
15. Concentration
16. Turnover

---

## 15.1 결과 지표

필수:

- CAGR
- Annualized Volatility
- Sharpe
- Sortino
- Max Drawdown
- Calmar
- Win Rate
- Profit Factor
- Average Trade
- Worst Trade
- Turnover
- Exposure
- Trade Count

추가:

- rolling Sharpe
- rolling drawdown
- regime별 성과
- year-by-year
- bull/bear
- high/low VIX
- high/low rate
- KRW strength/weakness
- BTC risk-on/off

---

# 16. Benchmark

V2 모델은 최소한 아래 benchmark와 비교한다.

### US

- SPY Buy & Hold
- QQQ Buy & Hold
- 현재 Kalman model

### KR

- KOSPI
- KOSDAQ 또는 전략 대상 benchmark
- 현재 Kalman KR model

### BTC

- BTC Buy & Hold
- 현재 Kalman Crypto model

---

# 17. OpenBB 도입 위치

OpenBB는 유용하지만 Phase 1에는 production server venv에 넣지 않는다.

권장 구조:

```text
OpenBB Service
    |
 REST / MCP
    |
Kalman Research/Data Layer
    |
Canonical Snapshot
    |
Feature Builder
```

즉:

```text
Toss Gateway != OpenBB runtime
```

으로 분리한다.

---

# 18. OpenBB를 나중에 쓰는 이유

장점:

- 여러 finance provider abstraction
- Python
- REST
- MCP
- AI agent 연동
- research UI 확장

하지만 현재 바로 넣지 않는 이유:

- dependency surface 큼
- 현재 gateway는 frozen sklearn dependency 존재
- 실거래 서버는 최대한 작고 deterministic해야 함
- 현재 필요한 기능은 yfinance/FDR/pykrx로 충분히 시작 가능

---

# 19. Freqtrade 판단

현재는 도입하지 않는다.

Freqtrade는 향후 다음 상황에서 검토:

```text
Kalman Crypto signal
  -> centralized exchange
  -> 직접 BTC/ETH execution
```

현재 Toss US execution과는 별개다.

---

# 20. Dependency 전략

## Production

현재:

```text
kalman-toss-gateway/requirements.txt
```

원칙:

- production-essential package만
- frozen sklearn compatibility 유지
- research package 최소화

---

## Research

별도:

```text
research/market_tools/requirements.txt
```

예상 후보:

```text
FinanceDataReader
finvizfinance
TA-Lib
vectorbt
pandas
numpy
pyarrow
```

OpenBB는 필요하면 다시 별도 환경으로 분리한다.

---

# 21. Phase별 구현 계획

## Phase 0 — Documentation / Architecture Lock

상태: **현재 단계**

해야 할 일:

- [x] 현재 Kalman 구조 확인
- [x] 기존 Tool overlap 확인
- [x] Tool decision 작성
- [x] production boundary 정의
- [x] dependency isolation 원칙 정의
- [x] point-in-time 원칙 정의
- [ ] 문서 검토 후 구현 시작

Production 영향:

```text
NONE
```

---

## Phase 1 — Market Data Provider Layer

### 신규 파일

```text
engine/market_data/__init__.py
engine/market_data/base.py
engine/market_data/schema.py
engine/market_data/yfinance_provider.py
engine/market_data/fdr_provider.py
engine/market_data/pykrx_provider.py
engine/market_data/validation.py
engine/market_data/snapshot.py
```

### 신규 script

```text
scripts/run_market_data_v2.sh
```

### 목표

- yfinance wrapper
- FDR adapter
- pykrx adapter
- canonical schema
- cross-provider report
- atomic snapshot

---

# 38. Phase 1A 실제 구현 결과

구현 브랜치에서 다음 파일이 추가되었다.

```text
engine/market_data/
├── __init__.py
├── base.py
├── schema.py
├── yfinance_provider.py
├── fdr_provider.py
├── pykrx_provider.py
├── validation.py
├── snapshot.py
├── cli.py
└── requirements.txt

scripts/
├── install_market_tools_v2.sh
└── run_market_data_v2.sh

docs/
└── MARKET_DATA_V2_RUNBOOK.md

tests/
└── test_market_data_v2.py
```

## Runtime isolation

```text
Production:
/opt/kalman/.venv

Market Tools V2:
/opt/kalman/.venv-market-v2
```

따라서 FinanceDataReader 도입으로 production의 고정 sklearn artifact dependency가 변경되지 않는다.

## Phase 1A 현재 provider map

```text
SPY
  -> yfinance SPY

BTC-USD
  -> yfinance BTC-USD
  -> FinanceDataReader BTC/USD

USD/KRW
  -> yfinance KRW=X
  -> FinanceDataReader USD/KRW

KOSPI
  -> yfinance ^KS11
  -> FinanceDataReader KS11
  -> pykrx index 1001
```

## Required / Optional source

Required:

- yfinance SPY
- yfinance BTC-USD

Optional cross-check:

- yfinance USD/KRW
- yfinance KOSPI
- FDR BTC
- FDR USD/KRW
- FDR KOSPI
- pykrx KOSPI

Required source가 실패하면 V2 runner는 FAIL/non-zero로 종료한다.

Optional source만 실패하면 DEGRADED로 기록하되 production pipeline에는 영향이 없다.

## 다음 검증

코드 구현만으로 Phase 1 전체 완료로 보지 않는다.

서버에서 다음을 확인해야 한다.

1. V2 전용 venv 설치
2. unit test
3. 실제 provider download
4. snapshot 생성
5. provider comparison 값 검토
6. Drive mount fail-closed
7. 기존 pipeline smoke test
8. production venv package 변화 없음

모두 통과한 뒤 Phase 1을 완료 상태로 변경한다.
