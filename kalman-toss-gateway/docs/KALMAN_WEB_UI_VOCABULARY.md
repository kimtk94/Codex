# Kalman Web UI Vocabulary Contract

Version: `kalman-ui-v1.1`

This vocabulary is the canonical user-facing terminology for Kalman Investment Hub. Internal API fields and strategy identifiers may remain English, but visible operational states should use the terms below consistently.

## Data state

- Overall healthy: **데이터 정상**
- One or more market snapshots need attention: **데이터 확인 필요**
- Individual snapshot inside its validity contract: **스냅샷 유효**
- Individual snapshot past `stale_after`: **스냅샷 만료**

Do not use **FRESH / STALE / DATA LIVE** as user-facing substitutes.

## Entry signal state

- Live-entry freshness window satisfied: **진입 신호 유효 (<90분)**
- Outside the entry freshness window: **진입 신호 만료**

The 90-minute entry cutoff is distinct from snapshot validity.

## Toss / execution connectivity

- Gateway/account link reachable: **Toss 연결됨**
- Gateway/account link unavailable: **Toss 오프라인**
- Server live-trading gate open: **자동매매 게이트 열림**
- Server live-trading gate closed: **자동매매 게이트 닫힘**
- Gate cannot be verified: **자동매매 게이트 확인 불가**

Do not use SERVER/BROKER/TRADING LINK as competing user-facing connection labels.

## Account and market-window state

- No holdings/open orders when required: **계좌 FLAT**
- Holdings or open orders exist: **계좌 보유/주문 있음**
- Fractional amount-order window open: **주문시간 가능**
- Window known closed: **주문시간 마감**
- Market calendar cannot be checked: **주문시간 확인 불가**

## Auto-trade state

- Signal age within the live-entry window: **진입 신호 유효 (<90분)**
- Signal age outside the live-entry window: **진입 신호 만료**
- Latest signal satisfies SHADOW_CANARY shape: **CANARY 조건 충족**
- Latest signal fails one or more SHADOW_CANARY fields: **CANARY 조건 미충족**
- Server-side read-only evaluator available and all real entry gates pass: **실행 조건 통과**
- Server-side evaluator available but a real entry gate blocks: **실행 조건 차단**
- Server-side evaluator unavailable: **실행 판정 확인 불가**
- Preconditions not fully satisfied: **대기**
- All server-side readiness gates satisfied: **진입 후보**

**진입 후보** means the read-only server readiness evaluator passed. It does not mean an order was submitted, accepted, or filled.

The web must not infer **진입 후보** from browser-side checks alone. Final readiness comes from the server evaluator that reuses the auto-trade gate helpers.

## Research vs live execution

- Top-6 portfolio/model what-if display: **연구 미리보기**
- Top-1 vs Top-6 forward comparison: **연구 벤치마크**
- R5.1 shadow lifecycle history: **R5.1 SHADOW · 모델 평가 기록**
- Mirrored bot orders/fills: **실매매 기록**

Research preview/benchmark/shadow results must never be labeled as live BUY/SELL execution.

## System identifiers kept as-is

The following may remain in English because they are identifiers or domain-specific contract names:

- R5.1
- SHADOW_CANARY
- Top-1 / Top-6
- Neon
- Toss
- FLAT
- RECON / Forward
- 4B / canonical bucket

## Required section names

- **자동매매 · 실행 조건**
- **R5.1 · 모델 순위**
- **연구 벤치마크 · TOP-1 vs TOP-6**
- **시스템 · Toss**
- **실매매 기록**

## Forbidden legacy labels

Do not reintroduce these visible labels:

- DATA LIVE
- MODEL ELIGIBLE NOW
- MODEL NOT ELIGIBLE NOW
- LIVE READY
- TRADING LINK ONLINE / OFFLINE
- BROKER LINK ONLINE / OFFLINE
- MODEL DATA FRESH / STALE
- MIRROR EMPTY

The v7.4.22 builder validates this contract in CI.


## Navigation hierarchy

- The top Command Center contains account summary, model state, benchmark, data health, and entry readiness.
- Detailed **내 계좌** and **실매매 기록** belong under the **운영** tab.
- The **통합** market view should compose current US/KR/Crypto snapshots directly instead of treating historical GLOBAL embedded component flags as current market state.
- On mobile, the primary market tabs stay on one horizontally scrollable row to prevent sticky sub-navigation overlap.
