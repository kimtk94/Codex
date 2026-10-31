# Kalman Market/Macro CI refresh — FRED credential and verification

## Credential origin
- Google Colab Secrets: `FRED_API_KEY` and `GITHUB_PAT`.
- Colab securely synchronizes only `FRED_API_KEY` to GitHub repository `kimtk94/Codex`, Environment `TaehoonServer`.
- Do not commit, print, export, or log credential values.
- For initial permission diagnosis, GitHub fine-grained PAT must permit Environments: Read and write.

## Production boundary
- Scheduled research workflow: `.github/workflows/kalman-market-refresh-ci.yml`.
- Its market dataset is a private, research-only Google Drive ZIP. It does not write to LIVE or to the existing production data paths.
- Normal schedule: Tuesday–Saturday 02:15 UTC (11:15 KST), after the preceding US cash-market close, including holidays/early close checks.
- GitHub Actions: https://github.com/kimtk94/Codex/actions/workflows/kalman-market-refresh-ci.yml

## How to verify
1. Inspect the most recent workflow run that started *after* the GitHub Environment Secret `FRED_API_KEY` was updated.
2. Require both `offline-tests` and `refresh` jobs to succeed.
3. Inspect the private latest ZIP `kalman_market_research_latest.zip` in Drive; read `readiness.json` and `fred/fred_status.json`.
4. Expect `fred_ready_series: 12`, `macro_completeness: FRED_READY_CURRENT_REVISED`, and `provider: FRED_OFFICIAL_API`. A workflow success alone is **not** sufficient: the market segment can pass while the FRED segment is degraded.
5. Confirm each series' `last_observation` and ZIP manifest SHA-256 hashes.
6. Keep `point_in_time_training_ready: false` until actual vintage-aware availability checks are implemented. The FRED API default provides latest-revised values and is not vintage-perfect for historical training.

## Failure checks
- `FRED_UNAVAILABLE` / `ReadTimeout`: inspect environment secret availability, outbound API requests, and provider status. Do not claim macro refresh success.
- `FRED_PARTIAL`: identify missing series by name and retain research-only status.
- `LAST_CLOSED_NYSE`: refuse publishing incomplete intraday daily bars.
- Never rewrite original Market_Data, Market_Features, or LIVE trading state to resolve a research-data failure.
