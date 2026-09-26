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

1. Stage 0 — audit KoGES files, aliases and organ feasibility.
2. Stage 1 — build the harmonized longitudinal biomarker panel.
3. Stage 2 — fit leakage-aware organ-age clocks with subject-grouped OOF prediction.
4. Stage 3 — estimate subject-level longitudinal organ-aging pace.
5. Stage 4 — quantify cross-organ discordance and cluster aging patterns.
6. Stage 5 — test pre-specified time-to-event outcomes when approved outcomes exist.
7. Stage 6 — optional PRS/genetic association bridge.
8. Stage 7 — integrate clock, pace, outcome and genetic evidence.
9. Stage 8 — sensitivity analyses: sex, complete-case, leave-one-organ-out and visit count.
10. Stage 90 — sync code, manifests, results and reports to Drive.

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

## Analysis guardrails

- Public KoGES files are for pipeline development/QC; final thesis inference must be rerun on the approved analysis dataset.
- Organ definitions are frozen before downstream outcome testing.
- Organ-age gap is age/sex residualized and primary clock performance is assessed OOF.
- Primary longitudinal pace requires at least 3 visits and at least 4 years of follow-up.
- PRS association is not MR and does not establish causality.
- Server shell scripts intentionally do not use `set -e`.
