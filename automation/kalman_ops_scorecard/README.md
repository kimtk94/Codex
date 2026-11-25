# Daily20 read-only operations scorecard

This is the active scorecard used by .github/workflows/kalman-daily20-ops-readiness.yml.

PR #1062 separates the current-run score count (20) from the cumulative Bull journal count (positive multiple of 20). The implementation is isolated here to avoid changing research/kalman_daily20/**, which is a protected Daily20 research/Drive writer push trigger. The original research/kalman_daily20/ops_readiness.py and its tests remain byte-identical to the legacy main version, for historical references only. Do not invoke the legacy module for new operations evidence.

This monitor only reads GitHub Actions run metadata and job logs; it cannot authorize data publication, trading, or research promotion. The schedule, journal writer, model, first-seal checks and Drive code remain unchanged. Any future cleanup of the legacy path requires separate writer-trigger review. The monitor's own workflow does not have a main-push trigger.
