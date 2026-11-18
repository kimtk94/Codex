# Controlled KoGES Data Contract

This is the **frozen pre-analysis contract** for the controlled multi-organ aging dataset.

## Current status

As of 2026-09-27:

- `/srv/is-analysis/data/multi_organ_aging/controlled` contains no supported data files.
- No A01/A02/A03-style integrated KoGES extract was found elsewhere under `/srv/is-analysis/data`.
- Public KoGES training files remain separate and must not be relabeled or copied into the controlled input directory.

## Accepted input layouts

The pipeline accepts either:

1. **one-wave-per-file** longitudinal exports, or
2. **integrated wide KoGES exports** using visit prefixes such as `A01_`, `A02_`, ..., potentially split across domain tables such as ANTHRO, BIOCHEM and SPIRO.

Multiple domain tables are coalesced at the participant-wave level. Conflicting nonmissing values are reported rather than silently discarded.

## Minimum longitudinal requirements

A controlled analysis is `GO` only when:

- participant identifier is resolvable,
- chronological age is available for at least 3 waves,
- at least 3 repeated visits are present,
- at least 3 organ systems meet the frozen minimum-feature rules.

## Expected organ feasibility from the reviewed KoGES integrated codebook

Likely:
- cardiovascular / vascular
- metabolic
- renal
- inflammatory / hematologic
- pulmonary

Hepatic remains provisional/HOLD unless the actual extract contains a third repeated age-independent hepatic marker in addition to AST and ALT.

## Leakage exclusions

Do not use:
- eGFR as a renal age-clock predictor,
- predicted FVC,
- predicted FEV1,
- percent-predicted spirometry

as age-clock predictors because these measures embed chronological-age/reference equations.

Observed eGFR may still be derived for renal outcome/validation work.

## Data safety

- Never commit individual-level controlled KoGES data to Git.
- Never commit direct identifiers.
- Run `scripts/check_controlled_drop.sh` first when a new controlled-data drop arrives.
- The drop inspector prints schema metadata only; it does not print participant-level values.
- Any possible direct-identifier-like column names are flagged before modeling.

## Execution order

1. `bash scripts/check_controlled_drop.sh`
2. readiness must return `GO`
3. `bash scripts/run_controlled_core.sh`
4. inspect Stage 1 mapping/ranges/conflicts
5. inspect organ-clock QC
6. freeze outcome definitions
7. only then run prospective outcome modeling

Controlled outputs remain isolated from the public prototype under:

`/srv/is-analysis/results/multi_organ_aging/controlled_analysis`
