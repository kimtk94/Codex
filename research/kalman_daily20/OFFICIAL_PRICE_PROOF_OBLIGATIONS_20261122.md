# Daily20 26-asset official-close and corporate-action proof obligations

Research-only continuation, 2026-11-22. Existing progress: **7/10 implementation milestones (70%)**, with **three scientific/operational acceptance milestones outstanding**. This audit does **not** mark a milestone as complete.

## Evidence-grade separation

- **25 equities/ETFs:** Alpaca SIP venue **M** close observations are research-only market-center references. They are neither independent consolidated 16:00 ET regular-closing price certification nor historical point-in-time venue identity. Yahoo `Close` is split-adjusted; `Adj Close` also reflects distributions; the ratio is same-vendor evidence and does not certify the corporate-action factor.
- **^VIX:** Cboe's index publication is a primary index reference. It does not require a stock split or cash dividend factor. The overall finality decision is still HOLD until the exact session record, vintage, and replay have sufficient official source evidence.
- **Historic issuer cash:** QQQ **2018-06-18** and QLD **2023-09-20** retain independently tracked cash-amount/unit-basis gaps. An annual distribution total, SEC-hosted third-party table, issuer schedule, or 2025 split context must not be promoted into an issuer-certified 2018/2023 cash event.

## Automated evidence obligations

The new `official_price_proof_obligations.py` reads five existing sources: `universe.json`, `source_finality/report.json`, `price_basis_bridge/report.json`, `corporate_actions/report.json` and `issuer_ca_gap_audit.json`.

It creates `research/official_price_proof_obligations/report.json` and `evidence_obligations.csv`, using a row per instrument and embedded SHA-256 digests of all five input files plus the final CSV. It checks exact **20+6** symbol membership, **25+1** factor applicability, session agreement, file-level market source lineage, 25 CA rows, the two issuer gap events, and false certification flags. Duplicate, missing, newly claimed certified, wrong-session or cross-symbol/tampered lineage records are hard CI failures.

The output is a **research HOLD evidence checklist**, not new official closing quotes, a price substitution, adjusted trading price, corporate-action rate, or a pass to train/live-trade. CSV obligations specify the next actual evidence needed per asset. Per-asset missing raw M references or vendor traces stay visible as HOLD instead of silently dropping rows.

## Remaining acceptance evidence

1. Obtain authenticated exchange consolidated regular-session EOD **25/25** and official index close **1/1** with timestamp, price basis, finality and venue/vintage scope; a research M print is insufficient.
2. Independently attest issuer split and cash distribution chains, share-unit basis and Yahoo repair transformation for **25** equities/ETFs; QQQ and QLD unresolved cash events must remain explicit.
3. Verify stable future same-session first-seals and matured four-session forward results before separate scientific approval. No historical journal rewrite, no live orders, no vendor price overwrite.

CI pass demonstrates completeness/integrity of **HOLD diagnostics only**. Source finality stays **0/26** and strategy approval remains HOLD.
