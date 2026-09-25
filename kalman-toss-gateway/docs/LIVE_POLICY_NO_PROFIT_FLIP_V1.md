# LIVE_POLICY_NO_PROFIT_FLIP_V1 — Frozen Prospective Shadow Candidate

## Decision

Freeze the exact policy below for prospective shadow validation only.

- Profit-flip: **OFF**
- Stop loss: **-3%**
- Take profit: **+20%**
- Model rotation: **OFF**
- Target exit: **4 canonical buckets**
- Historical replay feed: **SIP 04:00–20:00 ET + BOATS 20:00–04:00 ET**
- Cross-feed stale carry: **disabled**

No production policy, cron, order configuration, or managed-position state is changed by this freeze.

## Why this candidate exists

The exact SIP+BOATS 2025 replay reached 294/294 ready trades with all replay coverage medians equal to 1.0.

The full profit-flip policy improved drawdown versus FIXED_4 but did not survive the statistical gate. Turning profit-flip off produced stronger historical growth and slightly better drawdown:

- no-profit-flip vs FIXED_4 delta log-growth: **+0.1153719353**
- MDD delta: **+0.0444369197**
- positive folds: **2/2**
- one-sided bootstrap p: **0.0555944406**
- 95% bootstrap CI: **[-0.0000855268, 0.0010904249]**

It still failed the frozen historical survivor rule because the lower confidence bound remained slightly below zero.

Direct paired comparison of no-profit-flip versus the full profit-flip policy:

- delta log-growth: **+0.0928254344**
- MDD delta: **+0.0028157274**
- positive folds: **2/2**
- one-sided bootstrap p: **0.2310384481**
- 95% bootstrap CI: **[-0.0005755012, 0.0014513843]**

Therefore the data support **prospective testing**, not live promotion.

## Mechanism finding

Among 146 trades where the full policy exited on PROFIT_TO_LOSS_FLIP:

- 119 would have remained open without profit-flip and contributed a combined counterfactual delta of **+0.4051530560**.
- 27 would later have hit STOP_LOSS_3PCT and contributed a combined counterfactual delta of **-0.3052407358**.

The historical net favored disabling profit-flip, but the paired bootstrap was not statistically decisive. The candidate is therefore frozen without threshold tuning.

## Prospective protocol

Compare this frozen no-profit-flip shadow against the current full-policy shadow on the **same matched trade opportunities**.

Do not evaluate for promotion until both conditions are met:

1. at least **100 matched completed trades**, and
2. at least **30 U.S. trading sessions**.

Evaluate once after both minima are met. Do not repeatedly inspect and retune the policy during the window.

Primary endpoint: paired daily log-return delta.

Frozen gates:

- paired bootstrap 95% lower bound > 0
- one-sided bootstrap p <= 0.10
- MDD deterioration >= -2 percentage points
- matched-trade coverage >= 95%
- positive chronological folds >= 60%

Any policy or threshold change creates a new candidate version and restarts the prospective window.

## Interpretation guardrail

This candidate was selected after inspecting the 2025 historical sample. Those historical results are post-hoc evidence and are not independent confirmation. The next valid evidence is prospective shadow performance under the frozen contract.
