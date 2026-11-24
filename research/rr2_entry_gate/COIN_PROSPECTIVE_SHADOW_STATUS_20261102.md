# COIN prospective shadow OOS — verified implementation and activation gate (2026-11-02 KST)

**Decision: LIVE HOLD. Draft PR #496 only; no live broker, no main-branch deployment.**

## Verified execution

- GitHub Actions [#41324747469](https://github.com/kimtk94/Codex/actions/runs/41324747469): **SUCCESS**, offline chronology/privacy checks and real licensed SIP historical smoke; artifact `coin-prospective-smoke-public-seal`.
- GitHub Actions [#41325126322](https://github.com/kimtk94/Codex/actions/runs/41325126322): **SUCCESS**, improved original `2026` COIN V_unweighted source replay parity **208 historical model-evaluation dates / 46 signals**, plus strict source cutoff at last RTH close. Output artifact `coin-prospective-smoke-public-seal` has `original_2026_208_panel_46_signal_parity=true`, `commitment_input_cut_at_asof_RTH_close=true`, `RETROSPECTIVE_SMOKE_NO_OOS_CREDIT`.
- Frozen source commit: `cccbb80059ab626da0cbd76cd825f879870f6727`. Model is StandardScaler + LogisticRegression(C=1, class_weight=None, random_state=42, max_iter=1000) on the five original price+volume features. **All labels used for fitting must end before 2026-01-01.** 2026 historical test labels are used ONLY for retrospective exact parity verification, not training.
- Full training set and model coefficients remain in the ephemeral runner; no private SIP tape, raw quote rows, signal flag or prediction score published.

## Future prospective rules

1. **Start:** Monday 2026-11-02 NYSE session, **only after that RTH session fully closes**. First future entry, if a candidate is emitted, is the next NYSE session 09:45 New York time. 2026-10-30 smoke is pre-freeze historical and is never OOS.
2. **Eligible clock:** decision session date equals current America/New_York date; official NYSE session; time >= session close plus 20 minutes and strictly before next NYSE session opens. Any failure is a nontrading WAIT/HOLD.
3. **Data:** download Alpaca SIP 15-minute bars through a cutoff on an ephemeral GitHub runner. Hash input bounded **strictly before decision-day RTH close** so later after-hours additions cannot silently change the snapshot. Missing RTH bars, missing training labels, model provenance/count parity drift or source-date mismatch are failures, not substituted values.
4. **Public journal:** only a SHA-256 commitment over source-digest + frozen model-digest + full-precision private prediction + features and decision session; omit actual signal direction, score, raw data and trade levels. A proposed future run appends one `journal/coin/YYYY-MM-DD.json` entry to the separate `research/coin-prospective-audit` branch, with idempotent equality and conflict-on-difference checks. **This audit branch has not yet been created and its Git push path has not yet been exercised with a genuine future session**. Git commit history is tamper-evident but not unalterable by privileged administrators.
5. **Future evaluation NOT YET IMPLEMENTED:** once a session is sealed, evaluate whether its next-session 09:45 top-of-book quote was fresh <=1000ms, and if quoted-ask entry obeys fixed prior-day-low stop width 0.5–3%, ex-ante net RR>=2, target <=8%, and overlapping-position exclusion. A quote is **not** a confirmed fill. The predeclared 4-session horizon must expire before reporting results. Avoid disclosing signal event dates via row-level public artifacts.
6. Model/policy constants may not be retuned on future observed performance. A predeclared 30/50/100bp cost stress remains exploratory; baseline 30bp includes assumed slippage, so do not double-count quotes as an added fee. Require separate human review and several calendar regimes before any LIVE promotion.

## Operational deployment limitation — material

GitHub **cron and workflow_dispatch triggers are effective only for workflows on the repository default branch**. The new workflow `.github/workflows/kalman-coin-prospective-shadow.yml` is **currently only on Draft PR #496**, so `cron: 15 23 * * 1-5` (23:15 UTC / 08:15 next KST) **is NOT running automatically yet**. GitHub push to the PR branch deliberately runs only retrospective smoke, not prospective journal writes.

Activating automatic future OOS requires reviewing the research-only workflow and putting it **and the required source and test files** on the default branch, with its `TaehoonServer` Alpaca SIP secrets and `contents:write` audit branch capability. **Do not merge the entire large draft PR without review**; prefer a scoped research-only PR. Do not deploy to /opt/kalman, enable market orders or change the existing execution path.

## Remaining tasks and acceptance

- **A.** Approve and activate the isolated research-only workflow on default after code/scope review. Verify the first real 2026-11-02+ decision-day hash-only journal commit after the NYSE close and before the next entry session. Check repeat-run idempotence.
- **B.** Add the 09:45 quote-eligible, stop-first, target-limit-capped 4-session prospective settlement and uncertainty reports. Reconstruct and verify the sealed hash before consuming future bars, fail closed on any mismatch; retain **no LIVE approval**.
- Untouched OOS may not yet exist; historical smoke means only the pipeline works, not that strategy profitability or execution was proven.
