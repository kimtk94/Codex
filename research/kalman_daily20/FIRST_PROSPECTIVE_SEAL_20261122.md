# Daily20 first genuine prospective seal: pre-upload and remote readback proof

**Prepared 2026-11-22 KST, before 2026-11-23 NYSE closes.** No new-session forecast or returns have been observed at the time of preparation. The already sealed 2026-11-20 signals are legacy events; **their original 21-feature input snapshots do not exist and must not be backfilled.**

## The new independent evidence contract

`prospective_seal_attestation.py` is pure Python and reads **already-verified ZIP members**. For each genuine new sealed session dated **2026-11-23 or later**, it verifies:

| Evidence | Required match |
|---|---|
| 26 OHLCV close-day rows | Exactly the declared 20 core + 6 context symbols; finite OHLCV with valid high/low; canonical complete 26-row SHA-256 matches snapshot |
| 20 model symbols | Exactly 20 stock/ETF rows; each stored OHLCV equals the corresponding 26-price snapshot row |
| 20 × 21 as-of features | Exactly the fixed 21 ordered feature column names and numeric/null values; recompute each 21-element canonical SHA-256 |
| 40 fitted model records | Exactly 20 Bull + 20 Bear Logistic records, valid training-row count and training SHA-256, model parameter SHA-256 if fitted (null only if legitimately unavailable), fold status |
| 60 frozen event anchors | 20 Bull + 40 Bear/Rule journal SIGNAL events; verify the original full hash-linked journal (not only manifest SHA) and match each snapshot's event hash, candidate flag and probability |
| Capture environment and uncertainty | Source Actions run/commit, Python/numpy/pandas/sklearn versions, fixed training year cutoff, first-capture provisional price-finality HOLD |
| Replay preservation | The current run's stored first snapshot must pass existing byte-for-byte SHA/manifest/remote re-download. A later same-day replay reads the same stored original event hashes and snapshot; never substitutes the recomputed model probability. |

The new check executes **twice**: directly after building the signed results ZIP **before any Google Drive upload**, and again inside the existing remote results ZIP readback, after all ZIP member SHA-256 hashes have been checked and after actually downloading the pinned Drive file.

It adds `DAILY20_FIRST_SEAL_PREUPLOAD` to main workflow logs. Remote `daily20_stability_readback.json` now includes `prospective_first_seal_status`, `prospective_seals_deep_verified` and each sealed session's source run and original market/model/signal evidence summary. Earlier 2026-11-20 legacy sessions report `AWAITING_GENUINE_NEW_SESSION` and zero attested snapshots, not PASS.

### Boundaries

This proves **internal archival consistency**, not independent consolidated U.S. market-close authenticity, correct issuer corporate-action adjustment factors, valid filled prices, or future strategy returns. The source-finality gate remains **0/26 HOLD**; all snapshots are research-only; no broker, Neon, LIVE, model promotion, signals, price files or risk parameters are touched.

### Acceptance criteria after Nov 23

1. A protected Daily20 run after **2026-11-23 XNYS close**, before the following session opens, reports first seal 20 Bull + 40 Bear, 26 original price rows, 20×21 feature values, 40 model fingerprints, 60 original event anchors and `prospective_seals_deep_verified >= 1`; source finality remains HOLD.
2. The same run's pinned Drive ZIP is independently downloaded byte-identical and passes this deep check. Preserve run ID and snapshot SHA.
3. An independent same-session re-run confirms that **the original snapshot SHA and 60 original event hashes remain unchanged**, and reports any score drift as audit-only, never replacing the sealed journal.
4. Only after the fourth subsequent completed NYSE session may newly matured candidates be assessed as prospective observations. Existing November 20 signals are not retroactively normalized.

## Pointers

- Auditor: [prospective_seal_attestation.py](prospective_seal_attestation.py)
- Regression tests: [test_prospective_seal_attestation.py](test_prospective_seal_attestation.py)
- Integration: [publish_drive.py](publish_drive.py), [stability_drive_readback.py](stability_drive_readback.py)
- Historic drift: [Issue #884](https://github.com/kimtk94/Codex/issues/884)
- Existing results ZIP: [Google Drive](https://drive.google.com/file/d/1l-e4OLKS4qlDjNsf8TdkMsd5w3QouF4w/view)

Project engineering stays **70% (7/10 implementation milestones)** until first genuine prospective seal and later replay passes in a real market session.
