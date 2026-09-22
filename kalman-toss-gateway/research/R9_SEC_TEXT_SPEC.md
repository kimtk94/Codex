# Kalman R9 — SEC Text Novelty / Structured Event Research

**Pre-registered:** 2026-09-22
**Mode:** RESEARCH_ONLY
**Production/LIVE:** unchanged
**Champion:** R5.1_BASE_HGB
**Parent data layer:** R8-S SEC v2

## 1. Motivation

R8C1 showed that symbol-specific SEC event timing was substantially more competitive than global macro context, but did not beat frozen R5.1 on the alpha-promotion gates.

R9 does not retune R8 recency, half-life, item subsets, or weights.

Instead, R9 tests a genuinely new information axis:

**What did the corporate disclosure say, and how novel was that disclosure relative to the company's own prior disclosures?**

The R9.0 stage is data readiness only. No alpha model is fit.

## 2. Source

Input event registry:
- R8-S `kalman-r8-sec-corporate-events-v2`
- 8-K / 8-K/A only
- 93-symbol frozen R5 universe
- SEC primary filing document URL

Primary document source:
- `www.sec.gov/Archives/edgar/data/...`

No API key is used.

SEC fair-access contract:
- declared User-Agent
- sequential requests only
- minimum request interval = 0.35 seconds
- no more than one network request at a time
- cache successful downloads by source URL
- reruns reuse cache

## 3. PIT contract

Source event timestamp:
- EDGAR `acceptanceDateTime`

Conservative availability:
- `available_at = acceptanceDateTime + 5 minutes`

This remains stricter than relying on the raw EDGAR system timestamp alone.

No document-derived feature may be used before `available_at <= signal_as_of`.

## 4. Semantic text contract

Semantic 8-K items:
- 1.01 MATERIAL_AGREEMENT
- 2.01 ACQUISITION_DISPOSITION
- 2.02 EARNINGS_RESULTS
- 2.03 / 3.02 FINANCING_OBLIGATION
- 3.01 DELISTING_COMPLIANCE
- 2.05 / 2.06 RESTRUCTURING_IMPAIRMENT
- 5.02 MANAGEMENT_BOARD
- 7.01 REG_FD
- 8.01 OTHER_EVENT

Stand-alone 9.01 is not semantic text.

R9.0:
1. downloads the filing's primary document;
2. strips markup/scripts/styles;
3. finds explicit `Item X.XX` section boundaries;
4. extracts only registered semantic item sections;
5. does **not** silently substitute the entire filing if the semantic item section cannot be extracted.

The raw filing text is not a model feature in R9.0.

## 5. Leak-free novelty baseline

R9.0 computes deterministic lexical novelty without fitting a vocabulary on future documents.

Vectorizer:
- scikit-learn `HashingVectorizer`
- stateless
- lowercase
- English stop words
- word ngrams 1-2
- 2^18 dimensions
- L2 norm
- alternate_sign=false

Frozen features:
- `novelty_prev_symbol` = 1 - cosine(text, immediately prior usable semantic 8-K text for the same traded symbol)
- `novelty_prev_primary_bucket` = same, but prior event must have the same primary semantic bucket
- `semantic_text_chars_log1p`
- `numeric_token_ratio`

No sentiment, LLM score, return label, or price reaction enters R9.0.

## 6. Primary bucket priority

When a filing contains multiple semantic items, its primary bucket is the first match in this frozen order:

1. EARNINGS_RESULTS
2. ACQUISITION_DISPOSITION
3. MATERIAL_AGREEMENT
4. FINANCING_OBLIGATION
5. RESTRUCTURING_IMPAIRMENT
6. MANAGEMENT_BOARD
7. REG_FD
8. OTHER_EVENT
9. DELISTING_COMPLIANCE

This ordering is frozen before performance inspection.

## 7. R9.0 readiness gates

All required:
- input manifest is R8 SEC v2 and `sec_event_ready=true`
- >= 7,000 unique semantic source documents
- unique-document fetch success >= 95%
- cleaned-text parse success >= 95% of fetched documents
- explicit semantic item-section extraction >= 75% of fetched documents
- >= 5,000 usable extracted documents
- >= 80 / 93 symbols with >= 20 usable extracted documents
- usable document span >= 24 months
- >= 90% of usable non-first symbol documents have `novelty_prev_symbol`
- zero future-reference novelty construction
- zero production changes

If a gate fails, fix only the extraction/data contract. Do not lower the gate after observing alpha.

## 8. Future R9.1

R9.1 is **not admitted** by this specification.

If R9.0 passes, exactly one bounded text challenger may be separately preregistered.

The first bounded challenger should remain interpretable and low-dimensional:
- frozen R5 20 features
- R8 event-presence context may not be silently reused unless explicitly declared
- R9 text novelty / length / numeric-content features only
- no LLM API
- no post-result feature search

A later R9.2 may examine locally reproducible embeddings only under a separate preregistration.

## 9. Production invariant

R9:
- does not alter R5.1
- does not alter LIVE orders
- does not alter exits
- does not alter sizing
- does not write strategy_signal
- does not change R5-EXIT-V1
