# Historical paired-return residual cross-check: QQQ 2018 / QLD 2023

Research-only 2026-11-23 exercise. Main science status **7/10 (70%) implementation, 3 acceptance gates outstanding**; official-close verified **0/26** and independently certified issuer dividend/split adjustment factors **0/25**. No historical cash decisions or live trading changes.

## Evidence provenance and freshness

The original historical QLD/QQQ alignment export already resides in Google Drive `exports`, Drive file ID `1v9mM0l0-jLpXu81v6wfwJXHK3kSREsL-`. Its exact source identity is pinned by **SHA256 `87744adcc0dc288141ade3087f10ea270b613a4f9fe2fd6d1682aadfb55c8249`**, size **425,582 bytes**, rows **2,432**, and dates **2017-01-03 through 2026-09-04**. The file is historical and **stale** relative to the separate Daily20 market research as-of 2026-11-20, but it covers **both issuer disputes**: QQQ 2018-06-18 and QLD 2023-09-20. Its source is *not* an exchange price, issuer payout ledger, or corporate action adjusted price basis certification.

New workflow `.github/workflows/kalman-daily20-ca-alignment.yml` uses only the existing pinned service account identity, with a read-only Drive OAuth scope. On protected main, it retrieves the original file from Drive without overwriting or updating it, validates metadata and exact SHA256, then recomputes all 2,431 daily QLD/QQQ close-to-close returns and residuals from the stated closes. It writes a JSON report as an Actions artifact, not a production price file. If Drive access is missing, evidence is explicit **HOLD** and cannot be silently replaced by current Yahoo or by the attached local conversation file. PR tests run entirely offline on clearly synthetic examples; do not qualify as original financial evidence.

## Values from the source-file preliminary inspection (not independent vendor validation)

| Issuer exception | Same-source QLD minus 2× QQQ residual | Absolute residual rank among 252 prior sessions |
|---|---:|---:|
| QQQ 2018-06-18 | approx **+1.9492bp** | **22.22 percentile** |
| QLD 2023-09-20 | approx **−0.3753bp** | **4.76 percentile** |

QLD's published 2× daily performance is not exact because leveraged fund fees, financing, tracking deviations, overnight/rebalance effects and distributions may affect the comparison. A small single-day residual **does not establish payment or non-payment**, especially with potentially historical split-adjusted price series from one common feed. No exact dividend-to-price conversion is attempted because the vendor's 2018/2023 per-share cash field and the 2025 QLD split-adjustment basis are not independently authenticated. Invesco and ProShares/SEC historical issuer research remain distinct evidence, never overwritten.

## Compliance and reproducibility gates

- A different Drive source file size, binary digest, filename, or date coverage → hard failure.
- A changed date order, duplicate date, missing/not finite close, unknown schema, any return or residual not exactly reconcilable with closes to within 1e−9 → hard failure.
- Both issuer exception dates must be explicitly present with 252 preceding rows. Empirical absolute residual percentile is *descriptive* only, never significance of a dividend event.
- No trade signal, first-seal snapshot, signed journal, existing Drive results ZIP, live execution or price adjustment is touched.
- The final report explicitly carries `issuer_cash_payment_certified=false`, `issuer_nonpayment_certified=false`, `independent_factor_certified=false` and `independent_official_regular_close_certified=false` even on a successful file read.

Potential next step, after remote source readback confirms exact archive bytes: compare with original 2018 Invesco dated distributions and QLD's original 2023 SEC fund-specific report only as competing hypotheses. Do **not** promote a vendor amount, price adjustment or alpha based on the result.
