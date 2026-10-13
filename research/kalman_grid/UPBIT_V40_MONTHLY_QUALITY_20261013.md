# Kalman Grid V4.0 — strict monthly data gate

Date: 2026-10-13 KST. GitHub research branch only; no LIVE changes.

## Changes
1. `upbit_v39_monthly_collect.py` now only fetches absent symbol files rather than downloading both markets if either market's CSV is absent.
2. Collector runner passes **full requested month start and end** to `upbit_data_audit_v28.py`, so an internally continuous but truncated file is blocked.
3. `upbit_data_audit_v28.py`: time-zone-naive timestamps parsed as UTC, not server-local time; full-window endpoint checks added to the PASS gate.
4. `test_upbit_v40_month_quality.py`: four regression cases for naive UTC, year rollover, missing start-block and complete-window PASS.

## Execution status
All changes committed to research branch, but V4.0 tests and July/August data gathering **not yet executed on server** because Remote Desktop Commander quota unavailable. No fresh multi-month returns should be claimed.

## Research gate after running
- Rerun full test suite, audit July/August/September month-window endpoints.
- If any monthly source incomplete, reject comparisons; verify no-trade intervals separately.
- Run `upbit_v39_monthly_compare.py` and inspect 144 research PAPER scenarios across 3 months.
- The methodology is close-only hypothetical limit fills and fee-equivalent cost proxy, not real order execution.
- Protect LIVE trading; no modifications under `/opt/kalman`.
