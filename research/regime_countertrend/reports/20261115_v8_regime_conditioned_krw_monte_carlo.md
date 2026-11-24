# Kalman CFM-V8 — 원화 계좌 Regime 조건부 Monte Carlo (2026-11-15)

## 상태

- 코드/데이터 무결성 검증: **PASS**. [GitHub Actions #43713853203](https://github.com/kimtk94/Codex/actions/runs/43713853203), **151/151** unit/leakage tests, 결과 396행, SHA256 고정 10개 가상 원화현금 계좌/ETF 파일 + QQQ 1개.
- GitHub Artifact: **14160854030** (`regime-countertrend-results`).
- [Google Drive model_tests 보관본](https://drive.google.com/file/d/1-6WSA8Id_KaF7QlNajWGmcQB6MAlwx8C/view?usp=drivesdk), **4,340,357 bytes**.
- 데이터 기간: **2022-01-05~2026-11-04** V6 계좌 일별 원화 EOD 평가, 가상 거래와 전일 환율 평가. **실제 브로커 체결 또는 실제 통화 정산 아님.**
- 총 1,212개 계좌 일간 수익률 벡터를 보존한 공동 충격 부트스트랩, 미국 종목/ETF 원본 Yahoo 사후 조정가·USD/KRW 가격의 2026-11-15 빈티지.
- 연구 성과: **HOLD_REGIME_CONDITIONAL_HISTORICAL_STRESS_ONLY**. 역사 구간 반복 탐색, 전향 알파 검증 없음, LIVE 변경 없음.

## 왜 252일 단일 Regime을 폐기했는가

초기 구현은 하락 Regime 날의 `QQQ` 반등 수익률을 252일 동안 반복해서 뽑으면서도 시장을 계속 하락 Regime으로 유지했다. 이 가정은 합성 가격이 누적 반등하면 Regime 분류 자체가 바뀌어야 하는 경제적 논리를 위반하여 과장된 장기 수익률을 만들 수 있다.

따라서 **252거래일 단일 Regime 경로는 폐기**했고, `krw_regime_monte_carlo_v8.py`는 해당 요청을 테스트에서 **ValueError**로 차단한다.

현재 조건부 스트레스는 **5거래일·20거래일**만 허용, 평균 3·5·10거래일 연속 구간, 시나리오당 설정별 2,000회 (6 Regime × 2 horizon × 3 block × 2,000 = **72,000개 11자산 공동 경로**). 252일 전체 위험 확률은 **기존 별도 비조건부 V7 공동 블록 실험**을 참조한다. 합성 시나리오의 Regime 전이는 모델링하지 않는다.

## Regime 판단

- 당일 발생할 가상 계좌 수익은 해당 거래일 **전일 종가까지 확인된 QQQ 정보로만 분류**한다.
- 시장: QQQ 60거래일 수익률 >=+8% `UP`, <=-8% `DOWN`, 그 외 `SIDE`.
- 변동성: QQQ 일간 수익률 20거래일 표준편차 ×sqrt(252). `HIGH_VOL` 기준은 2021-12-31 이전 가격으로 계산한 75% 분위수 (**연율 0.2370 = 23.70%**).
- `HIGH_VOL`, `LOW_VOL`은 `UP/DOWN/SIDE`와 **겹치는 분류**; `DOWN_HIGH_VOL`은 하락 Regime의 하위집합. 6개 행을 상호 배타적인 상태의 발생 확률처럼 합산할 수 없음.
- 동일 날짜 11개 원화 계좌/ETF/원화 및 달러 현금 경로에서 **하나의 공통 날짜 인덱스**를 사용해 가격·환율 동시 충격을 보존. Regime 이탈 시 순차 블록을 종료하고 해당 Regime 내 다른 과거 일자로 재시작한다.
- 결과는 `단일 Regime이 단기간 지속된다고 가정했을 때의 스트레스 분포`일 뿐, 실제 Regime 지속 확률을 반영한 Markov path forecasting이 아님.

## 이용 가능한 실표본

| 상태 | 관측 일수 | 연속 시퀀스 수 | 최장 연속 구간 | 최대 연도 집중도 | 판단 |
|---|---:|---:|---:|---:|---|
| UP | 406 | 40 | 63일 | 30.8% | 조건부 기술통계 |
| DOWN | 166 | 25 | 32일 | **78.3% (2022년)** | **HOLD 집중도** |
| SIDE | 640 | 66 | 89일 | 24.2% | 조건부 기술통계 |
| HIGH_VOL | 373 | 11 | 143일 | 61.4% | 조건부 기술통계 |
| LOW_VOL | 839 | 12 | 354일 | 27.4% | 조건부 기술통계 |
| DOWN_HIGH_VOL | 159 | 23 | 32일 | **79.9% (2022년)** | **HOLD 집중도** |

모든 6개 조건은 실험 최소 표본일 80일, 분리된 연속 구간 8개를 넘겼지만 DOWN/DOWN_HIGH_VOL 두 조건은 한 해 편중도가 75%를 초과. 이는 **실행 가능한 계산과 실증 신뢰도는 다르다**는 뜻이다.

## 20거래일 스트레스 결과 — 평균 요청 블록 5일

`P(원금손실 종료)`은 **단기 가상 계좌의 최초 1천만 원 미만으로 종료한 MC 경로의 비율**이며, 개별 주식 신호의 승률이 아님. 수익률은 KRW, 매도 대금은 달러로 유지·재사용, 가상환전 편도 10bp.

| 상태 | V4 P(원금손실) | V5 P(원금손실) | V4 P(MDD <=−5%) | V4 P(QQQ보다 저조) | V4 중앙값 수익률 | V4 수익률 하위 5% |
|---|---:|---:|---:|---:|---:|---:|
| UP | 42.60% | 43.40% | 5.90% | 59.85% | +0.60% | −4.05% |
| DOWN | 39.95% | 43.40% | 15.25% | 76.45% | +0.85% | −4.46% |
| SIDE | **75.20%** | **74.10%** | **29.55%** | 65.40% | **−2.10%** | **−7.13%** |
| HIGH_VOL | 54.30% | 54.85% | 25.10% | 45.55% | −0.40% | −6.07% |
| LOW_VOL | 57.55% | 58.40% | 16.20% | 73.30% | −0.70% | −5.82% |
| DOWN_HIGH_VOL | 43.00% | 45.80% | 17.05% | 74.70% | +0.72% | −5.11% |

주요 결론: **중립 Regime에서 원화 가상계좌가 취약**하다. 그러나 이 표로 곧바로 `SIDE` 주문 금지를 결정하면 사후 규칙 최적화이며, 새로운 외부 구간에서 동결된 조건으로 재검증해야 한다.

20일 위험에서 블록 3·5·10일 민감도: V4 중립 원금손실 비율 **74.4%, 75.2%, 74.9%**로 계속 높은 구간; 평균 블록 5일에서 실제 관측 Regime 경계로 평균 **3.35일**마다 재시작하므로 *요청 평균 블록 길이=실현 평균 길이*가 아님. 결과 CSV에 `effective_mean_block`과 `forced_state_boundary_restart_fraction`을 별도 보관.

DOWN과 DOWN_HIGH_VOL 수익률이 플러스로 나온 것은 당시 2022년 반등 및 USD/KRW 노출 영향이 섞인 결과일 수 있어, 실전 방어 성과를 입증하지 않는다. 특히 Regime를 20일간 인위적으로 지속시키는 시나리오는 과거 동일 환경이 반복될 때를 가정한다.

## 파일, 재현 및 평가 경계

- `research/regime_countertrend/krw_regime_monte_carlo_v8.py`: 6개 이전 종가 Regime, 5/20일 조건부 공동 부트스트랩, 비용 및 원화 스프레드 구분.
- `research/regime_countertrend/test_krw_regime_monte_carlo_v8.py`: Regime 미래누출, 조건부 표본 부족 HOLD, 252d 고정 불합리성 차단, 동일날 FX/ETF 충격 보존 검증.
- `monte_carlo_pinned_vintage_v7.json`: QQQ 가격 CSV SHA256 `e733e2ac3c1d6388573333cc51ea5003e1cd45e1609db1d1e47d9af5ad0c31f6`, 기존 KRW 10개 파일 SHA256.
- GitHub Actions `regime-countertrend-research.yml`: 동일 과거 GitHub Artifact `14159488405` 데이터를 내려받아 해시 검증 후 **추가 Yahoo 재조회 없이** 위험 분포 산출.
- 결과 경로: `regime_mc_v8/dated_prior_close_regime_labels.csv`, `regime_coverage_and_year_concentration.csv`, `regime_conditional_krw_monte_carlo.csv` (396행), `decision.json`.
- 모든 산출물 `promotion_allowed=false`. 실제 브로커 체결/외환 전환 기록은 없음. **시장 LIVE/Neon 쓰기 없음**.

### 이후 연구 우선순위

1. **고정 V7 JSON의 2026-11-16 이후 관측을 실제로 성숙시키고, 동일한 원화 평가 및 위험 분포와 비교**. 현재 독립 미래 관측 손익 미검증.
2. **Regime transition-aware 모델** (과거 관측으로 학습한 Markov 또는 동결 HSMM 전이)과 현재 5/20일 보수 스트레스 결과 비교; 상태 지속을 임의로 1년 고정하지 않는다.
3. 실제 달러 현금·환전 체결·매수/매도 원장으로 원화 실계좌 PnL 대사. 유효 가격/체결 증거 없이는 LIVE 자동 승격 금지.

**최종 판정: REGIME_MONTE_CARLO_SYSTEM_PASS / V4·V5 연구 모델 수익성 HOLD / REAL_BROKER_PNL_HOLD / LIVE_NO_CHANGE.**
