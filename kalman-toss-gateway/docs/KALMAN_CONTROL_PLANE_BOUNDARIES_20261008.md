# Kalman Control-Plane Boundaries — 2026-10-08

Status: **CONTROL-PLANE FREEZE / NOT DEPLOYED TO LIVE SERVER**

Branch: `chore/control-plane-boundaries-20261008`

## 1. Server working-tree freeze

The server working tree must not be pulled, rebased, checked out, or deployed over until its local changes are reconciled.

Freeze records created on 2026-10-08 KST:

- GitHub tracked-WIP branch: `freeze/server-20261008-0142`
- tracked-WIP commit: `446cf48c4b997fd0bbd7c2d45ee28e76dbdd27e1`
- local complete snapshot: `/home/taehoon/kalman-freeze/20261008T0142KST`
- snapshot contains status, binary patch, untracked-file archive, repo bundle, and SHA256 manifest.

The original server branch and working tree were intentionally left in place.

## 2. Codex and Vercel source of truth

Canonical application source is `kimtk94/Codex`.

The current Vercel project `kalman-investment-hub-v2` is deployed by the audited Codex builder/CLI pipeline:

`Codex -> build_investment_hub_v7436_shadow_freshness.py -> source manifest -> staged Vercel production build -> smoke tests -> promote`

At the time of this freeze, Vercel Git metadata still points to `kimtk94/IS_Analysis_V3`. That Git link is **not** the canonical Kalman web source and must not be used as a release trigger.

Until the project has a directly deployable checked-in Vercel root, do not replace the audited builder with Git auto-deploy. The safe target state is:

- Codex is the only source repository.
- IS/CKD research repositories cannot trigger Kalman Investment Hub deployments.
- production promotion happens only after candidate smoke tests.
- Vercel production remains read-only with respect to broker execution.

## 3. Execution boundary matrix

| Layer | Strategy / policy | Broker order permission |
| --- | --- | --- |
| LIVE R5.1 Top1 | `R5.1_BASE_HGB` + `R5_LIVE_TOP1` + explicit confirmation | possible only after all existing LIVE gates pass |
| LIVE R5.1 Conditional | `R5.1_BASE_HGB` + `R5_LIVE_CONDITIONAL` + valid conditional confirmation | possible only through the dedicated conditional executor and existing LIVE gates |
| Pure SHADOW | SHADOW research/model outputs | **never** broker orders |
| SHADOW_CANARY | LIVE execution policy consuming explicitly eligible SHADOW-tagged signals | can place broker orders only with its separate LIVE confirmation; do not confuse this with pure SHADOW |
| R5.2 | `R5.2_*` / `R5.2*` research candidates | **never LIVE under the current boundary** |

## 4. R5.2 promotion rule

`R5.2_COST_AWARE_RESEARCH_V1` remains research-only. Its existing config already declares:

- `research_only=true`
- `live_execution=false`
- `broker_orders=false`
- `NO_LIVE_PROMOTION_FROM_4H_SCORE_OVERLAY`

This control-plane change adds a second independent barrier: R5 LIVE policies accept only `R5.1_BASE_HGB`. Changing only `AUTO_TRADE_STRATEGY_VERSION` to an R5.2 value therefore fails closed.

Promotion of an R5.2 candidate requires a deliberately reviewed code change, a new LIVE freeze document/version, and the full revalidation checklist. An environment-variable edit alone is insufficient.

## 5. Readiness/executor consistency

The previous branch had a split contract:

- `auto_trade.py` recognized `R5_LIVE_TOP1`.
- `readiness.py` recognized `R5_LIVE_CONDITIONAL` but not `R5_LIVE_TOP1`.
- conditional LIVE supports both legacy 20k confirmation and 5k-chunk confirmation, while readiness recognized only the legacy token.

This branch centralizes these boundaries in `engine/execution_boundary.py` and makes readiness represent both LIVE R5.1 policies without granting R5.2 execution permission.

## 6. Deployment rule

This branch is a safety/control-plane change only. It must not be copied to `/opt/kalman/app` or used to alter active LIVE settings until tests pass and the server WIP reconciliation is complete.
