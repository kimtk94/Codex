# OpenBB V5 Cboe vs Existing Kalman Alignment (2026-10-26 KST)

## Verified runtime evidence
- CI run: https://github.com/kimtk94/Codex/actions/runs/40206625818
- Artifact ID: 12604135324 (4 CSV files and summary.json)
- Keyless OpenBB V5 Cboe historical query starting 2026-09-01: QQQ, QLD, SPY and TQQQ each returned **37 rows**, observed 2026-10-25 15:22:51 UTC. Last returned date was 2026-10-22.
- Existing uploaded baseline `QLD_QQQ_daily_alignment.csv` had 2,432 rows, 2017-01-03 through 2026-09-04. This local baseline file is not committed to the PR.
- Four common dates (2026-09-01 to 2026-09-04 inclusive), 8 QQQ/QLD symbol-date pairs.

## Overlap comparison
| Symbol | Close exact matches | Maximum absolute open gap | Maximum volume gap (vs baseline) |
| --- | ---: | ---: | ---: |
| QQQ | 4/4 | 0.05 USD | 13.39% |
| QLD | 4/4 | 0.05 USD | 0.80% |

Daily per-date volume deviations vs baseline (provider minus baseline):
- QQQ: 2026-09-01 -3.81%; 09-02 -13.39%; 09-03 -2.32%; 09-04 -11.31%.
- QLD: 2026-09-01 -0.58%; 09-02 -0.80%; 09-03 -0.41%; 09-04 -0.46%.

## Decision
**CLOSE_MATCH, VOLUME_REVIEW**. Retain Alpaca baseline; do not replace volume or train volume-sensitive models on mixed feeds without examining venue coverage, feed entitlement, settlement revisions, session coverage, rounding, and adjusted-price policy.
Only 4 common trading days and daily bars were compared. No claim regarding 15-minute/1-hour data availability or full historical fidelity.

## Next gate
- Export Cboe bars to normalized provider CSV and run `provider_parity.py` on a larger overlapping window.
- Add configurable volume and OHLC parity gates; report provenance metadata.
- Evaluate historical coverage and constraints for 15m/1h separately.
- Keep all work in GitHub CI/Shadow. No LIVE rules or execution modifications.
