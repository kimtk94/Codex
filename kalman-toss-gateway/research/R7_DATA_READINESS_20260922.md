# R7.0 Data Readiness Snapshot — 2026-09-22

## Current Neon state

| Layer | Current state | R7.1 status |
|---|---:|---|
| macro_release_observation | 0 rows | BLOCKED |
| macro_policy_repricing_observation | 0 rows | BLOCKED |
| macro_shadow_evaluation_v1 | 4 rows | DIAGNOSTIC ONLY |
| news_article | 839 rows | CORPUS PRESENT |
| news_feature_snapshot | 172 rows | GLOBAL/MACRO ONLY |
| US symbol-level news snapshots | 0 rows | BLOCKED |
| PIT earnings revisions | no dedicated table detected | BLOCKED |

## News corpus observations

The current corpus includes official publisher-timestamped sources and recent GDELT observed-proxy records. It is useful for event/provenance infrastructure, but it is **not yet a historical 93-symbol company-news feature panel**.

Current `news_feature_snapshot` rows are:

- market = GLOBAL;
- symbol = GLOBAL;
- feature version = `macro-event-feature-v1`;
- recent snapshot history only (2026-09-20 onward);
- coverage confidence ≈ 0.65.

Therefore these snapshots cannot be used as a stock-specific R7 news challenger.

## Macro observations

The macro feature machinery already exposes useful diagnostics such as DGS2 daily change and DGS2-DFF level spread, but the actual event-surprise and event-repricing providers are currently unavailable/blocked because:

- no populated release-observation table;
- no populated policy-repricing table;
- no US consensus-surprise provider;
- no event anchor for intraday US2Y reaction.

R7 will not reinterpret daily-rate proxies as event-level surprise/repricing.

## Immediate build order

1. Populate PIT macro release observations.
2. Populate event-linked US2Y/policy repricing observations.
3. Backfill/audit symbol-level company-news features.
4. Add PIT earnings revision source.
5. Only then run the corresponding R7.1 challenger.
