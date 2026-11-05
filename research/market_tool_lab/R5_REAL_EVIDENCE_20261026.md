# R5.x real research evidence inventory — 2026-10-26

Read-only inspection of private Drive artifacts; raw data and account credentials remain outside GitHub.

## R5.1 prospective shadow
Folder: https://drive.google.com/drive/folders/1j4kcVkzTdBydtVBeqe5IRWVDkN1tuFh7
- Signal log `r5_1_signal_log.parquet`: https://drive.google.com/file/d/1fnsf-ZfSjhqP_njkOTjdQNcPZvGJsqAK/view
- Entry log `r5_1_trade_entry_log.parquet`: https://drive.google.com/file/d/1AyriA1cIgOqDzKl5KAIsI2IgYSVUCLYC/view
- Outcome log `r5_1_outcome_log.parquet`: https://drive.google.com/file/d/1EDFyspA4C7_zxd7yDn5QaUDQevvPDFCJ/view
- Status `r5_1_status.json`: updated 2026-10-16 19:40 UTC. State ACCUMULATING_PROSPECTIVE_EVIDENCE, production_enabled=false, trade_enabled=false. 185 signal rows, 46 entries, 45 mature outcomes across 30 days; net10_cum_return=-0.06156479350207267, net10_mdd=-0.0897144136157576, hit_rate=0.4. Minimum review gate 100 mature outcomes / 60 distinct days. This gate is NOT met.

## R5.2 macro ablation
Folder: https://drive.google.com/drive/folders/13pV4RVhui1otmmw0gPs_c1FsWYASJmI1
- Trade ledger `r5_2_trade_ledger.parquet`: https://drive.google.com/file/d/1gTiZyC18o8omdHZB2Wl_bptANtaPgu4f/view
- Selection decision: MACRO_NOT_PROMOTED, no survivors, no selected R5.2 primary; generated 2026-09-02 22:55 UTC.
- Historical ablation leaderboard (each 1,352 trades):
  - R52C0_BASE_HGB: net10 cumulative 1.4863207382 (148.63%), MDD -0.2265885177 (-22.66%), hit 0.5051775.
  - R52C1_HGB_MACRO: cumulative -0.1732735035 (-17.33%), MDD -0.4194123605 (-41.94%), hit 0.4822485.
  - R52C2_HGB_MACRO_INTERACTIONS: cumulative 0.2110986115 (+21.11%), MDD -0.2965919050 (-29.66%), hit 0.4859467.
- These are distinct evaluation setups; NEVER directly rank historical R5.2 cumulative returns against prospective R5.1 results.

## Priorities / guardrails
1. Download private Parquet in a restricted evaluation environment and inspect actual schemas and timestamps. None of the discovered Parquet bytes has been interpreted yet.
2. Export precisely time-eligible entries and mature outcomes; prohibit future/label columns from becoming signal inputs.
3. Align R5.1 entries with historical OHLCV at actual entry timestamp; daily-close proxy is NOT equivalent to live fills.
4. Compare actual baseline and fixed +3/-3/4-day barrier under matching entry events and realistic costs, stop-first for daily same-bar ambiguity; show MDD only after constructing nonoverlapping portfolio equity.
5. Prospective results and historical ablations remain separate; never promote R5.2 macro or change LIVE config based on this evaluation.
