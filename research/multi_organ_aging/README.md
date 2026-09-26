# Multi-organ Aging

KoGES longitudinal prototype for organ-specific biological aging.

## Shared project location

This project intentionally lives beside the ischemic-stroke work.

- Code root: `/srv/is-analysis/IS_Analysis_V3`
- Project code: `/srv/is-analysis/IS_Analysis_V3/research/multi_organ_aging`
- Shared data root: `/srv/is-analysis/data`
- Project data: `/srv/is-analysis/data/multi_organ_aging`
- Results: `/srv/is-analysis/results/multi_organ_aging`
- Drive mirror: `gdrive:IS_Analysis_V3/MULTI_ORGAN_AGING`

Raw individual-level data must never be committed to Git.

## Research question

Can repeated routine biomarkers identify discordant aging rates across metabolic,
renal, hepatic and vascular systems, and do those organ-specific aging patterns
predict future deterioration or multimorbidity beyond chronological age?

## Pipeline

1. Stage 0 — audit available KoGES files and variables.
2. Stage 1 — build harmonized longitudinal panel.
3. Stage 2 — fit organ-age models using baseline out-of-fold prediction.
4. Stage 3 — estimate subject-level longitudinal organ-aging pace.
5. Stage 4 — quantify cross-organ discordance and multi-organ acceleration patterns.
6. Stage 5 — define longitudinal incident/deterioration outcomes.
7. Stage 6 — test organ-aging metrics against outcomes.
8. Stage 7 — optional genotype/PRS bridge.
9. Stage 8 — generate integrated summary tables and report.
10. Stage 90 — sync code/results to Drive.

## Quick start

```bash
cd /srv/is-analysis/IS_Analysis_V3/research/multi_organ_aging
bash scripts/00_init_project.sh
python3 -m pip install -r requirements.txt
bash scripts/run_all.sh
bash scripts/90_sync_drive.sh
```

Server shell scripts intentionally do not use `set -e`.
