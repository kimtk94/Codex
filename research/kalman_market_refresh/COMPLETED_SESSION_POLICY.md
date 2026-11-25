# Completed-session research cutoff policy (proposal only)

Incident #1030 / run 45602794486: Yahoo returned a November 25 VIX row before the completed November 24 XNYS cutoff. The existing validation correctly blocked the bundle.

This offline-only proposal freezes an explicit aware clock, calculates the XNYS close plus 30 minutes (including holidays and early closes), and returns an exclusive provider end date for the 14 US-session keys only. Five non-US keys retain their existing collection semantics. It also provides a non-mutating tail diagnostic that counts even null-close post-cutoff rows, checks the cutoff OHLC, and returns HOLD metadata. It does not certify the provider, inspect every historical OHLC row, or approve a derived prefix.

No changes to workflow, shared provider, schedule, source archive, feature output, data writer or LIVE. Before integration, test separately fetched US and non-US windows, freeze a single reference clock through fetch/validation, retain observed tails in private evidence, require coverage and raw/TA timestamp and value reconciliation, regenerate features and manifests from the same completed prefix, and preserve every existing QC gate. Do not merge merely because a synthetic test passes. A push to main may start existing refresh workflow.

## Offline staged integration contract

`split_selected_universe` consumes the actual selected 19-key config and produces two lossless group configurations with one frozen clock and exclusive US end date; it executes nothing. `reconcile_staged_us` compares an independently fetched bounded US frame with the observed eligible prefix (only `retrieved_at` may differ), checks raw/feature timestamp and symbol alignment, and recomputes features twice using the explicitly supplied builder. Revisions, adjustment/source-asof changes, extra tails, missing cutoff, or feature differences remain HOLD. Synthetic tests use a deterministic feature builder, not live TA-Lib. No workflow calls, archive publication, actual refetch, source certification or change to non-US semantics. A separate integration review must wire the real engine builder, verify all 19 assets and original QC gates, and use a private approved test target before deployment.


## Actual public provider probe

`provider_cutoff_probe.py` is an isolated diagnostic using the unchanged YFinanceProvider, actual TA-Lib builder and local PyArrow round trips. It freezes the actual execution clock (not a retrospective vintage), compares independent unbounded and exclusive-end US requests, and leaves the non-US request end unset. It reports aggregate coverage and OHLC/feature diagnostics only, never source certification or a releasable archive. The initial PR-only CI probes VIX, SPY, SMH and USDKRW; the other 15 keys are not actually fetched by this trial. No Drive credentials, production environment, scheduler, write dispatch, or raw data artifact. Temporary raw/features are removed on exit. Strict differences or unavailable public provider remain HOLD. Technical reproduction does not imply complete coverage/QC or PIT readiness. Actual workflow integration requires separate review.
