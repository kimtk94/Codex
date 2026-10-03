# R5.1 Conditional Allocation Challenger Freeze

Status: **RESEARCH CHALLENGER — NOT LIVE**

Frozen candidate:

- Gap quantile: **0.35**
- Confidence quantile: **0.30**
- Rank2 allocation when score gap is close: **50%**
- Rank1 allocation when score gap is close: **50%**
- Cash allocation when Rank1 confidence is low: **50%**
- Rank1 allocation when confidence is low: **50%**
- Otherwise: **Rank1 100%**
- Threshold estimation: lagged expanding quantiles only
- Minimum history: 100 admissions
- Base exit: FIXED_4 + Friday-flat
- Base cost: 10 bps

Decision order:

1. If Rank1 confidence is in the lower 30% of prior observations:
   - Rank1 50%
   - Cash 50%
2. Else if relative Rank1-vs-Rank2 score gap is in the lower 35% of prior observations:
   - Rank1 50%
   - Rank2 50%
3. Else:
   - Rank1 100%

Promotion gates before any LIVE integration:

- Cost stress at 10/20/30/50 bps.
- Threshold perturbation around GQ 30/35/40 and CQ 25/30/35.
- Holding-horizon stress at FIXED_3/FIXED_4/FIXED_5 with Friday-flat.
- Year-by-year stability.
- Block-bootstrap support.
- Prospective shadow only after a live full-candidate ranking source exposes Rank1 and Rank2 scores at each admitted signal.

Important: the existing prospective R5.1 signal log contains the selected Top1 signal, not a complete Rank1/Rank2 cross-sectional ranking. Do not fabricate Rank2 and do not enable this challenger in LIVE until that data contract exists.
