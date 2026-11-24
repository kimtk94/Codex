# KALMAN challenger research decision record — 2026-11-24

**Decision: RESEARCH_HOLD. No prospective activation, paper execution, or LIVE approval.**

## Scope and evidence

This is a retrospective consolidation, not another optimized strategy or a new
prequential protocol. The frozen protocol is
`challenger_prequential_protocol.json` SHA256
`e72ad78b04e5667539f50cd8076e578c9b20ae36e3549c22b543e2fb91b2f93d`.
Historical cutoff 2026-11-23; 727 XNYS sessions from 2024-01-02. Original
source run 45383657032, data/research artifacts 14914498151/14915426739.
Historical replay/diagnostics passed Actions run 45415978062, head
adfdb1aa1da2f050c19e6c34d4be51e2e1501617. This is not independent
prospective evidence. Draft #1056; research issues #509 and #879.
The incumbent Daily20 journal and native schedule are separate.

## Research priority, not an investment rating

| Family | Grade | Disposition |
|---|---|---|
| K1 | A | Frozen primary comparator |
| K1+K3 | A | Frozen primary challenger (20 names, 30bp) |
| K3 | B | Descriptive component challenger |
| K2 barrier EV | C | Separate protocol/review required; exploratory |
| K2 original Logistic | D | Shadow only; strict RR2 bracket integration not supported |
| K1+K2+K3 | D | No promotion; incremental old K2 not supported |

The 16-name and 50bp scenarios remain descriptive stress controls. Do not
select them, delete high/low PnL names, modify thresholds or switch models
using this repeatedly inspected history. K2 pooled barrier and incumbent
per-symbol Logistic differ in samples, fitting and execution assumptions.

## Evidence synthesis

On the pinned 20-name 30bp strict TIGHT rank-first daily proxy: K1 +13.09%,
K3 +6.23%, K1+K3 +22.25%, old K2 -0.32%, all three +20.62% cumulatively.
K1+K3 MDD -3.90%, annualized daily volatility 4.73%, Sharpe 1.495,
140 trades, average post-entry open exposure 11.37%, close exposure 7.51%.
Calendar-year cumulative returns +12.28%/+5.57%/+3.13% (2026 partial).
50bp independently gated scenario +19.02%; 16-name 30/50bp +26.98/+21.59%
but 2026 -0.75/-1.39%. Strict TIGHT geometry cannot pass the 100bp RR2 gate
with the frozen cost and distance constraints; no-trade is not validation.
The separately trained 20-name pooled K2 EV>=0 barrier challenger
+8.87/+2.82% at 30/50bp on its own historical cohort; no established advantage.

20-day paired historical block bootstrap: primary combined-minus-K1
p=0.18688, Holm 1; cash comparison also fails Holm. Selection diagnostics
DSR ~0.519 (89 distinct broad paths) and CSCV broad 10-block PBO ~44.44%;
incomplete adaptive-search ledger. Monte Carlo resamples observed history,
not a forecast: primary median +22.23%, p05 +6.86%, MDD p05 -8.30%.
Matched-realized-vol SPY +14.98%, QQQ +12.30%, but 0/40 Holm significant
at 5/20/60 blocks. Static weights fitted ex post and timing controls
conditional. Exposure-weighted proxy-factor intercept +1.20% annual
arithmetic, raw bootstrap p=.37476 (20-day block), Holm 1.0; prior-year
fit 2026 residual -0.15%. Not official factors or causal alpha.

Locked admitted-cohort exclusions: all 91 full-period returns positive;
primary top3 exclusion +11.31%, SEMI exclusion +10.55%, 0/91 Holm.
Nearly half of primary historical net PnL from AVGO/GOOGL/MU, no
counterfactual replacement. Extra adverse 20bp per side on unchanged
primary cohort gives +9.28%, only 49/140 planned exact RR>=2; 50bp per
side -7.62%, 0/140. Distinct 193 historical trade windows, only 6 inspected
with existing QQQ/QLD 15m bars (24/769 symbol-sessions); no certified
quote fills. 187 missing windows, 745 symbol-sessions, 19,322 regular
15m bars needed. Historical price basis and source finality unresolved.
Public CI does not receive private intraday data. Zero-interest cash and
nominal friction are assumptions, not measured fills.

## Frozen forward estimand and looks (unchanged)

Primary comparison 20_30_K1+K3 minus 20_30_K1: paired arithmetic daily net
equity returns on all XNYS sessions including verified cash-only sessions.
Start only after separately reviewed, independently anchored ACTIVATE
before first eligible open; no catch-up or retroactive timestamp.
Complete contiguous prefix AND fourth-session maturities are required.

| Look | Purpose | Alpha |
|---|---|---|
| 126 sessions | Descriptive only | 0 |
| 252 sessions | Conditional statistical diagnostic | 0.02 |
| 504 sessions | Conditional statistical diagnostic | 0.03 |

Two-sided null-centered joint circular moving-block mean test, 20-session
blocks, 10,000 replications, plus-one p; positive mean difference additionally
required. Minimum 20 nonoverlap four-session active groups and 8 active
months for formal diagnostic. No extra looks, no optional extension, no
choosing a favorable cost/cohort/model. Sum of fixed look alpha budgets .05.
A conditional threshold pass is **not promotion**. Formal economic alpha
requires a separately frozen forward exposure/risk-matched benchmark; the
historical ex-post matched controls are not that protocol. A new hypothesis
must be versioned and reviewed before seeing its forward outcomes.

## Admission and incident handling

Existing execution contract: 30bp base and 50bp descriptive stress, both
linear/exact net RR >=2, gross stop 0.5–3%, gross target <=8%, TIGHT
0.75/2.25 ATR, next-open daily price proxy only; max 5 reserved slots,
20% opening equity per slot, shared cash, no borrowing, no replacement,
early proceeds reserved through fourth close, gap stop at open and target
capped, both-touch stop first. No price basis mixing or silent interpolation.

Reject individual candidates failing RR/distance, price validity, duplicate
or capacity/cash constraints. Missing/uncertified data are a HOLD, not a
legitimate no-trade or zero PnL. Freeze evidence and stop prospective
publication on broken provenance, missed deadline, journal/anchor mismatch,
invalid mark/settlement or ledger mismatch. Retain incident evidence;
do not rewrite previous events or repair a historical timestamp. A broken
complete prefix cannot be treated as complete via a new record. Any new
study start requires a distinct reviewed prospective protocol/activation.

Proposed operational *review trigger*, not an implemented statistical stop:
research equity drawdown >=10% from its own high-water mark, or material
execution-cost breach, warrants manual risk review and a continued HOLD.
Do not use interim p-values or PnL to choose the look or switch strategy.
Do not truncate the research series and then claim the frozen inference;
record suspension explicitly. No broker position exists in this research.

## P0 evidence gates before any activation

All remain externally reviewed gates, not a mutable boolean checklist.
Historical CI PASS or an archived receipt cannot discharge them.

| Gate | Evidence required | Current disposition |
|---|---|---|
| #884 reproducibility | frozen input/model/environment digests; deterministic replay and reviewed discrepancy resolution | OPEN |
| #907 source finality | 26/26 independently timestamped regular-session closes, verified adjustment basis and re-download | OPEN |
| #1045 native scheduler | actual native first/replay/watchdog deliveries, independent missing-run detection and reviewed resolution | OPEN |
| Point-in-time universe | listing-date membership, delisting/corporate-action and availability evidence | UNVERIFIED |
| SIP execution | authorized private source, quote/basis/time/size and order-fill feasibility, missing data explicit | UNVERIFIED |
| Evidence publication | reviewed producer; protected independently retrievable timestamped anchors before entry | UNVERIFIED |
| Ledger/curve export | independent re-execution of all marks and settlements against immutable evidence | UNVERIFIED prospectively |
| Archive | Taehoon authenticated create-only readback and independently retained evidence; separate from public PR | manual historical archive verified; automatic OAuth worker not provisioned |

External reviewer must verify evidence source and freshness, not simply
accept a local JSON flag. The current verifier does not authenticate anchor
origin or reconstruct from a user-supplied mark alone. Stage producer creates
proposals, not publication or activation. No access/permission expansion,
private credentials or protected dispatch in public PR jobs.

## Decision after a mature look

1. Invalid/incomplete evidence or insufficient activity: HOLD; do not score
   as a zero-return day.
2. Complete eligible 252/504 look with nonpositive mean or p above its
   allocated alpha: threshold not met, no promotion. Retain results; no
   unscheduled looks. At 504 if neither allocated look met the positive
   threshold, record unsupported incremental benefit and close this
   confirmatory study without retroactive reselection.
3. Complete look meeting the threshold: conditional research evidence only.
   Independent evidence reviewer and separate economic/implementation review
   must still assess cost, risk, drawdown, concentration and executable
   quote evidence. Paper-trading authorization, broker credentials or live
   capital allocation require a separate explicit decision outside this PR.

The accompanying consolidation CLI cross-checks regenerated historical reports
and protocol scope. It **always** emits RESEARCH_HOLD, never activation or
approval. It cannot attest external source finality, scheduler or anchors.
No prospective records generated by this decision.
