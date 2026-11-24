# Daily20 next US session first-seal / second-pass immutable handoff — 2026-11-22

**Progress: 7/10 (70%) · 3 scientific acceptance gates remain · all 26 independent official closes HOLD.** No live orders or strategy changes.

## Confirmed next XNYS session

- As of Korea Sunday, Nov 22, the latest completed US session is **Friday Nov 20**. The next full regular NYSE trading date is **Monday Nov 23**, pending actual market close. This report does **not** pre-create that session's forecasts.
- Existing [Daily20 GitHub Actions](https://github.com/kimtk94/Codex/actions/workflows/kalman-daily20.yml) first scheduled run: **02:40 UTC on Tue Nov 24 (11:40 KST)**; second independent run: **04:40 UTC (13:40 KST)**, both using calendar-aware last fully closed NYSE date.
- If genuine new signal sealed on Nov 23, first maturity for the Nov 23 session is **Monday Nov 30 U.S. close** (Nov 24,25,27,30 subsequent XNYS days; Nov 26 Thanksgiving closed). Existing Nov 20 events can first mature on **Friday Nov 27 U.S. close** (Nov 23,24,25,27).
- Historical 2026-11-20 Bull and Bear cohorts: 20+40 sealed events, **zero genuine original 21-feature/fitted-model first snapshot**. Never backfill or represent the 11/20 cohort as a new prospective first seal.
- Two-run scheduling is already present; **GitHub scheduled dispatches are best effort, not execution guarantees**. A delayed first run after the next session's opening may produce a missed-window HOLD and must never backfill.

## New independent before/after control

`next_session_two_pass_contract.py` runs ONLY inside protected `main` (not in PR, where protected Drive cache is intentionally unavailable), in two read-only phases:

1. **preflight**, after 26-asset market QC and before Bull/Bear forward writes. Reads the SHA256-validated pinned previous results ZIP; authenticates all original members, original Bull and Bear signed event chains, original first-seal snapshot hashes and previous trading date. Uses XNYS trading calendar and actual UTC wall time. Emits:
   - `FIRST_GENUINE_SEAL_EXPECTED`: the following session really closed, no cohort exists yet, and the post-close +45min / next-open admission window is valid → expect 20 Bull + 40 Bear new events.
   - `SAME_SESSION_REPLAY_EXPECTED`: the complete 20+40 cohort already exists with an original first input snapshot → expect **0** added events, all original bytes retained.
   - `LEGACY_REPLAY_NO_20261120_ORIGINAL_FEATURES_HOLD`: pre-v1 historical event exists without original snapshot → cannot retrofit evidence.
   - `FIRST_SEAL_WINDOW_MISSED_HOLD`: the correct new session has **no** original events but the capture window expired → no backdating, no false new seal.
   - Partial 20/40 cohorts, future-dated prior Drive archive, unsafe or altered signed ZIP, stale QC or wrong as-of calendar are hard errors.
2. **postflight**, after Bull and Bear seal writing and after 21-feature/40-model provenance freezing. Confirms the new event counts agree across Bull report, Bear report and stability report. Critically, both journal files must begin with the **exact bytes** of the previously validated journal. All original snapshots of older sessions must retain exact SHA256 bytes. If 20+40 new events are expected, verify those **60 hash-linked original events** carry this same Actions run ID, and run the independent `prospective_seal_attestation.attest_snapshot` check on original 26 price bars, 420 signal-day feature numbers, 40 model hashes and 60 original event anchors. Any mismatch aborts publication.
   - On second run, expected 0 new events; the first snapshot's SHA256 must be **exactly equal to its earlier saved bytes**. Input/probability changes are retained as replay incident/HOLD, not silently overwritten or converted into fresh signals.
   - On old Nov 20, the missing snapshot is not recreated.

The two reports (`research/two_pass/preflight.json` and `research/two_pass/report.json`) are included in the existing research Actions artifact and pinned Drive ZIP using existing research packaging. The independent remote ZIP readback still verifies every member SHA256; it also has the separate deep prospective seal proof already installed, so the new gate complements but never replaces it.

## Falsification and independence

New offline tests simulate Nov 23 first capture, Nov 24 replay, missed admission, future prior ZIP, wrong session, incomplete cohorts, changed original journal bytes, wrong run ID, falsified live promotion, partial event count, and bad original snapshot bytes. Real experiments DO NOT create synthetic investment signals or publish user-facing performance metrics.

**Scientific status stays HOLD** regardless of the outcome of this contract. We still lack authorized independent regular closes for 26/26, issuer-certified corporate action factors for 25/25, and 4-XNYS-session genuinely matured forward results. Only live post-Nov-23 original + replay evidence can advance the prospective acceptance gate.
