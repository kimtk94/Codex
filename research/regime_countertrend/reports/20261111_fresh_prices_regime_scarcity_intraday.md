# QLD/QQQ 신규 데이터 및 Regime 신호 부족 감사 — 2026-11-11

**평가 상태:** `FRESH_PRICE_DATA_PASS`, `ORIGINAL_ENTRY_SIGNAL_N=0`, `INTRADAY_PRICE_COVERAGE_PASS_WITH_QQQ_OPEN_WARNING`, `LIVE_EXECUTION_HOLD`.

**CI:** [Kalman Regime Countertrend Research #43002216434](https://github.com/kimtk94/Codex/actions/runs/43002216434) · 57/57 tests PASS.

## 재현 가능한 공개 가격 데이터

- 기존 고정 Drive 원천: 2017-01-03 ~ 2026-09-04, QLD·QQQ 2,432거래일.
- 이번 신규 Yahoo Finance 1일봉: **2026-09-08 ~ 2026-11-10, QLD/QQQ 공통 46거래일**.
- 총 연구용 연결 길이 2,478거래일. 2026-09-04의 교차 앵커(QLD 90.68 USD, QQQ 718.96 USD) 값이 새 출처와 일치.
- 소스 확인값(11/10 종가): QLD 78.20 USD, QQQ 674.76 USD. Stooq는 유효한 CSV를 반환하지 않았고, Yahoo Finance chart API에서만 통과.
- 원본 데이터는 GitHub Actions Artifact에 날짜별 분리 저장: `fresh_oos/paired_public_daily_prices.csv`, `fresh_oos/provenance.json`.

## 신호 부족 분석

이전에 고정된 신호만 재평가했으며 새 기간을 보고 기준을 변경하지 않았음.

- 시장 구분: QQQ 60일 수익률 **상승(+8% 이상) 0일 / 하락(−8% 이하) 2일 / 중립 44일**.
- QQQ 60일 수익률 범위 −10.591% ~ +7.359%. QLD 5일 수익률 범위 −18.560% ~ +12.489%.
- QLD 5일 −3% 이하 16일, +3% 이상 8일. 하지만 각각 상승·하락장 Regime과 **동시에** 충족한 날은 0일.
- 고정 기존 전략의 신규 거래 0건. 확정 평가 가능 42일, 후속 4거래일이 아직 경과하지 않은 날짜 4일.
- MACD 히스토그램 3일 개선 18일, RSI 3일 상승 18일, 두 신호 동시 개선 14일.
- **해석:** 기술지표 필터 단계 전에 상위 시장 Regime/역추세 조건에서 기회가 없었다. 따라서 기회 0건을 수익률 0%, MDD 0%, PASS로 오해하면 안 됨.

## 신규 Yahoo Finance 15분봉 정규장 유효성

- 수집 구간: 2026-09-15 ~ 2026-11-10 (UTC+NY 거래일 기준).
- QLD: 1,066 bars / 41 session, 각 세션 26 bars 모두 완비 (41/41).
- QQQ: 1,066 bars / 41 session, 각 세션 26 bars 모두 완비 (41/41).
- 정규장 첫 15분 시가와 일봉 시가 비교에서 QLD 최대 차이 **3.86bp**.
- QQQ 최대 차이 **17.55bp**, 이상 날짜 **2026-11-10 한 건** (>10bp QC 경고). 원인은 확정되지 않음.
- 15분봉 2개 종목 총 2,132개 시장 가격 봉을 확보했으나 브로커 체결 사실이나 실제 슬리피지의 증거는 아님.
- 증분 시장데이터 중 2026-09-08 ~ 09-14 구간은 이번 15분봉에 포함되지 않음.
- Yahoo 15m API는 기간 제한이 있는 회전형 원천이므로 실행 Artifact와 해시로 검증 가능한 스냅샷 보관.
- CI Artifact에 `fresh_15m/QLD_15m_rth.csv`, `fresh_15m/QQQ_15m_rth.csv`, 세션별 정합성·출처 JSON 저장.

## 판단/다음 설계

1. 상위 Regime이 46일 중 44일을 SIDE로 분류해 무거래가 된 구조를 **입장 조건과 별도로 진단**. V2 후보의 Regime 설계는 개발용 장기 과거 구간에서 먼저 정의해야 함; 46일 데이터를 보고 맞춤형 최적화 금지.
2. 시장 Regime (장기 추세) × 변동성 Regime × RSI/MACD 반전 상태의 다층 분석을 SHADOW 연구에서 비교하고, 신규 시점 또는 새로운 자산 집합으로 독립 재검증.
3. 실제 첫 15분 시가 체결 시뮬레이션 전에 일봉/15분 시가 차이 10bp 초과 원인 재검증 및 실제 주문·체결 시각·수수료 독립 대사.
4. 고정 비용 20/40/80bp와 갭·양쪽 장벽 충돌 처리, 실제 보유 겹침/잔고 제약을 계속 유지.

**금지:** LIVE 전략 자동 승격, Neon 거래 DB 변경, 신규 데이터 기반 임계값 재최적화, 실제 주문 체결 검증 완료 주장.
