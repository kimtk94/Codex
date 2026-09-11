# Kalman Market Data V2 — Phase 1A Runbook

> 상태: 구현 및 GitHub Actions CI 검증 완료 / 서버 실데이터 smoke test 전 / production 미연결
>
> 이 runner는 Market Tools V2의 shadow data collector다. Neon strategy signal, frozen model, Toss 주문 상태를 읽거나 쓰지 않는다.

## 1. 범위

Market Data V2는 `config/market-data-v2-universe.json`을 source of truth로 사용한다.

기본 그룹:

- US: SPY, S&P500, QQQ, IWM, DIA, SOXX, SMH, Nasdaq, MU, IONQ
- BTC: BTC-USD, IBIT, FBTC, COIN, MSTR
- COMMON: VIX, US10Y, DXY, HYG, LQD, TLT, GLD, USD/KRW
- KR: KOSPI, KOSDAQ
- Cross-check: FinanceDataReader 및 pykrx

yfinance의 SPY와 BTC-USD는 required source다. 그 외 provider는 현재 shadow 단계에서 optional/cross-check source다.

Universe 변경은 Python 코드를 수정하지 않고 JSON config에서 수행한다.

## 2. Production 격리

기존 production Python:

```text
/opt/kalman/.venv
```

V2 전용 Python:

```text
/opt/kalman/.venv-market-v2
```

FinanceDataReader는 V2 전용 venv에만 설치한다. 기존 `kalman-toss-gateway/requirements.txt`는 수정하지 않는다.

## 3. V2 환경 설치

배포된 서버 코드 기준:

```bash
sudo /opt/kalman/app/scripts/install_market_tools_v2.sh
```

설치 확인:

```bash
/opt/kalman/.venv-market-v2/bin/python - <<'PY'
import yfinance
import FinanceDataReader
from pykrx import stock
print("market-v2 dependencies: OK")
PY
```

## 4. 환경변수

권장값:

```env
KALMAN_MARKET_V2_OUTPUT_DIR=/mnt/gdrive/Market_Data/v2
KALMAN_MARKET_V2_START_DATE=2024-01-01
KALMAN_MARKET_V2_END_DATE=
KALMAN_MARKET_V2_UNIVERSE=/opt/kalman/app/config/market-data-v2-universe.json
```

`END_DATE`는 비워두면 provider가 가능한 최신 구간까지 조회한다. V2 venv 경로를 바꿔야 하는 특수한 경우에만 shell 환경변수 `KALMAN_MARKET_V2_VENV`를 export한다. 이 값은 `/opt/kalman/.env` 설정이 아니다.

## 5. Manual run

기본:

```bash
sudo /opt/kalman/app/scripts/run_market_data_v2.sh
```

기간을 짧게 제한한 smoke run:

```bash
sudo /opt/kalman/app/scripts/run_market_data_v2.sh \
  --start-date 2026-08-01
```

별도 output directory 테스트:

```bash
sudo /opt/kalman/app/scripts/run_market_data_v2.sh \
  --start-date 2026-08-01 \
  --output-dir /opt/kalman/data/Market_Data/v2-smoke
```

## 6. Output

기본 구조:

```text
$KALMAN_MARKET_V2_OUTPUT_DIR/
├── raw/
│   ├── yfinance/
│   │   ├── yf_spy.parquet
│   │   ├── yf_btc.parquet
│   │   ├── yf_usdkrw.parquet
│   │   └── yf_kospi.parquet
│   ├── financedatareader/
│   │   ├── fdr_btc.parquet
│   │   ├── fdr_usdkrw.parquet
│   │   └── fdr_kospi.parquet
│   └── pykrx/
│       └── pykrx_kospi.parquet
├── validation/
│   └── provider_comparison.json
└── market_data_v2_run_status.json
```

각 parquet 옆에는 provenance sidecar가 생성된다.

예:

```text
yf_spy.parquet
yf_spy.metadata.json
```

metadata에는 provider, provider symbol, request period, row count, checksum, write timestamp 등이 기록된다.

## 7. Validation report

현재 비교:

```text
BTC      : yf_btc      vs fdr_btc
USD/KRW  : yf_usdkrw   vs fdr_usdkrw
KOSPI    : yf_kospi    vs fdr_kospi
KOSPI    : pykrx_kospi vs fdr_kospi
```

확인:

```bash
cat /mnt/gdrive/Market_Data/v2/validation/provider_comparison.json
```

주요 필드:

- overlap_rows
- first_overlap
- last_overlap
- primary_last_close
- secondary_last_close
- last_close_relative_diff
- mean_abs_close_relative_diff
- max_abs_close_relative_diff
- daily_return_correlation

현재 단계에서는 provider 차이에 대한 자동 투자 판단 threshold를 적용하지 않는다. 먼저 실제 차이 분포를 축적한다.

## 8. Run status

```bash
cat /mnt/gdrive/Market_Data/v2/market_data_v2_run_status.json
```

상태:

### READY

required provider가 정상이고 optional provider도 정상.

### DEGRADED

required provider는 정상이나 하나 이상의 optional cross-check provider가 FAIL/DEGRADED이거나 provider comparison 자체가 실패.

이 경우에도 production에는 영향이 없다.

### FAIL

required source인 yfinance SPY 또는 BTC가 실패.

runner는 non-zero exit code를 반환한다.

## 9. Google Drive guard

output이 `/mnt/gdrive` 아래라면 runner는 실행 전에 mount 상태와 read 가능 여부를 확인한다.

mount가 없으면 local directory를 대신 만들어 쓰지 않고 실패한다.

이는 Drive 장애 시 동일 경로의 로컬 파일을 실수로 생성하는 것을 방지한다.

## 10. Lock

동시 실행 방지:

```text
/opt/kalman/state/market-data-v2.lock
```

동일 job이 겹쳐 실행되지 않는다.

## 11. Test

repository root의 gateway directory에서:

```bash
cd kalman-toss-gateway

PYTHONPATH=. /opt/kalman/.venv-market-v2/bin/python \
  -m unittest tests.test_market_data_v2 -v
```

unit test는 외부 network 호출 없이 canonical schema, provider comparison, atomic parquet snapshot을 검증한다.

## 12. 현재 하지 않는 것

Phase 1A에서는 다음을 하지 않는다.

- cron 등록
- Neon write
- strategy_signal 변경
- 기존 Unified pipeline 데이터 source 교체
- 기존 RSI/feature 변경
- Finviz 사용
- TA-Lib 사용
- vectorbt 사용
- Toss 주문

## 13. Phase 1A 검증 체크리스트

- [ ] V2 venv 설치 성공
- [ ] production venv package 변화 없음
- [ ] SPY snapshot 생성
- [ ] BTC yfinance snapshot 생성
- [ ] BTC FDR snapshot 생성
- [ ] USD/KRW 두 provider snapshot 생성
- [ ] KOSPI yfinance/FDR/pykrx snapshot 생성
- [ ] metadata sidecar 생성
- [ ] SHA-256 존재
- [ ] provider comparison JSON 생성
- [ ] Google Drive mount failure 시 fail-closed
- [x] unit tests 통과 (GitHub Actions)
- [ ] 기존 US/KR/CRYPTO pipeline smoke test 영향 없음

이 체크가 끝난 뒤 Phase 2 Finviz screener snapshot 구현으로 넘어간다.
