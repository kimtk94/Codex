# Multi-organ Aging

KoGES longitudinal prototype for organ-specific biological aging.

## Shared project location

This project shares the ischemic-stroke infrastructure while keeping project data
and outputs isolated.

- Code root: `/srv/is-analysis/IS_Analysis_V3`
- Project code: `/srv/is-analysis/IS_Analysis_V3/research/multi_organ_aging`
- Shared data root: `/srv/is-analysis/data`
- Project data: `/srv/is-analysis/data/multi_organ_aging`
- Results: `/srv/is-analysis/results/multi_organ_aging`
- Drive mirror: `gdrive:IS_Analysis_V3/MULTI_ORGAN_AGING`
- Git branch: `research/multi-organ-aging-20260927`

Raw individual-level data must never be committed to Git.

## Research question

Can repeated routine biomarkers identify discordant aging rates across metabolic,
renal, hepatic, vascular, inflammatory/hematologic and pulmonary systems, and do
those organ-specific aging patterns predict future deterioration or multimorbidity
beyond chronological age?

## Pipeline

1. Stage 0 — audit files, aliases and organ feasibility.
2. Stage 0C — audit controlled-data readiness before any controlled-data modeling.
3. Stage 1 — build the harmonized longitudinal biomarker panel.
4. Stage 2 — fit strict-reference organ-age clocks.
5. Stage 2B — generate subject-level cross-fitted longitudinal organ-age scores.
6. Stage 3 — estimate full-window organ-aging pace.
7. Stage 3B — estimate pre-landmark pace for prospective inference.
8. Stage 4 — quantify cross-organ discordance; clustering remains exploratory.
9. Stage 5 — controlled outcome association layer when approved data exist.
10. Stage 5 public — public-data landmark workflow validation.
11. Stage 5B — bootstrap, orthogonalized-pace and PH robustness checks.
12. Stage 5C — discrete-time complementary-log-log analysis for visit-observed incident diagnoses.
13. Stage 6 — optional PRS/genetic association bridge.
14. Stage 7 — integrate evidence.
15. Stage 8 — descriptive sensitivity analyses.
16. Stage 90 — sync code, manifests, results and reports to Drive.

## Quick start

```bash
cd /srv/is-analysis/IS_Analysis_V3/research/multi_organ_aging

bash scripts/00_init_project.sh
python3 -m pip install -r requirements.txt
bash scripts/run_all.sh

# After reviewing outputs:
bash scripts/90_sync_drive.sh
```

For future Git refreshes on the server:

```bash
bash scripts/update_from_git.sh
```

Before controlled KoGES analysis:

```bash
bash scripts/run_controlled_readiness.sh
```

After readiness returns `GO`, run the isolated controlled phenotype pipeline:

```bash
bash scripts/run_controlled_core.sh
```

Controlled outputs are written under
`/srv/is-analysis/results/multi_organ_aging/controlled_analysis`
so public-prototype results and models are not overwritten. The controlled core
runner intentionally stops before outcome association modeling.

Current public-prototype checkpoint:
- `docs/PUBLIC_PROTOTYPE_CHECKPOINT_20260927.md`
- `docs/REPO_LAYOUT.md`

## Analysis guardrails

- Public KoGES files are for pipeline development/QC; final thesis inference must be rerun on the approved analysis dataset.
- Organ definitions are frozen before downstream outcome testing.
- Primary within-cohort phenotypes use subject-level outer cross-fitting: a participant's longitudinal trajectory is scored only by models that did not train on that participant.
- Organ-age gap is age/sex residualized using training-fold information only.
- Primary longitudinal pace requires at least 3 visits and at least 4 years of follow-up.
- PRS association is not MR and does not establish causality.
- Server shell scripts intentionally do not use `set -e`.
