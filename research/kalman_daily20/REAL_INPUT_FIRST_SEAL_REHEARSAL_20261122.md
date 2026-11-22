# Daily20 real archived input first-seal contract rehearsal — 2026-11-22

**Independent scientific status remains HOLD.** This is a PR-only, credential-free integration test, never a prospective signal or trading action.

The first-seal deep attestation added by PR #954 had 17 synthetic-data contracts, but those fixtures did **not** exercise the exact `stability_gate.make_current_snapshot` production generator on independently archived, actual 26-asset 2026-11-20 price + 21-feature data. A mismatch in float normalization, fitted-model hashing, missing Bear fit status, or frozen Bull/Bear source linkage would otherwise first surface on the inaugural real November 23 seal when the publisher is in its fail-closed path.

## Verification

The new `first_seal_real_input_rehearsal.py`, run **only on pull requests** after `latest_research_scores.csv` exists:

1. Loads the real CI 26-asset closed-session market bars, 26 TA-Lib Parquet feature datasets and 20 model scores, the same inputs used by the main Daily20 research pipeline.
2. Calls **real** `stability_gate.make_current_snapshot` (20 actual Bull and 20 actual Bear fitted predictions; all 420 actual signal-day features). Temporary SHA anchors are explicitly tagged synthetic.
3. Produces **20 Bull + 40 Bear/Rule synthetic SIGNAL events** using the repository's existing real SHA256 journal-hash implementations, with source GitHub run SHA, Bull-to-Bear linkage and same observed probabilities. All generated journal bytes exist in memory only.
4. Validates both full synthetic journal hash chains; calls the **same production snapshot generator again** with those 60 test hashes and checks the actual 26 prices, 420 features, 40 fitted-model hash records and score values did not change across the two computations.
5. Runs `prospective_seal_attestation.attest_snapshot` (the exact production deep checker) on this historical **2026-11-20 source date** with a synthetic provisional source-finality HOLD fingerprint, and requires 26/420/40/60 linkage.
6. Writes a non-sensitive, explicit `REAL_INPUT_SYNTHETIC_EVENT_CONTRACT_PASS` report to `$RUNNER_TEMP` only. It is not included in the two pinned Drive ZIPs, not added to any Bull/Bear journal, never treated as an original post-2026-11-20 snapshot and not counted as scientific readiness.

The test must reject a synthetic event with an invalid journal chain, duplicate symbols, or any difference between original and repeated price/feature/model inputs. Errors block the PR merge. The 2026-11-23 *actual* first-seal remains required; the rehearsal alone does not prove official 16:00 exchange close, future date admissibility, or settled P&L.

## Acceptance criteria

- New five offline tests PASS.
- The PR's real market/feature/model integration step outputs 26 real OHLCV rows, **420 real feature values**, 40 actual fitted/unavailable Bear model provenance records, and 60 in-memory simulated event hashes, with the original generator and independent verifier agreeing.
- Existing annual OOS, historical pricing, CI write guard and all workflows remain unchanged.
- Main remains research HOLD, official independent close certification 0/26 and zero actual new prospective seals until U.S. market close on November 23.
