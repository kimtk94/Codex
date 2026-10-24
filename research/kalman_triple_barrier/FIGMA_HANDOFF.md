# Kalman Triple Barrier Lab — Figma handoff v1

Status: DESIGN SPECIFICATION ONLY. The Figma file exists but editing was blocked by Starter MCP rate limit.

Figma target: https://www.figma.com/design/jqg65pZF8X3mcdci8gQpAC
Production UI: https://kalman-triple-barrier-lab.vercel.app
Source: research/kalman_triple_barrier/web/index.html

## Data truth and visibility
- R5.2 historical baseline: 24 fold records (3 strategies × 8 folds), from r5_2_fold_summary.csv; this is NOT a Triple Barrier result.
- Triple Barrier actual R5.1/R5.2 metrics remain N/A until matched historical signals and OHLC pass backtest.
- Poll the CI and published data every 10 seconds in the web UI. The existing historic fold replay reveals one row every 10 seconds; this is a presentation cadence, NOT a CI compute interval.
- Never display placeholder return, simulated backtest P&L or fake green success numbers.
- Browser-visible public outputs must contain aggregate research metrics only: no keys, account positions or personally identifiable data.
- Live trading controls are NOT part of this screen.

## Frame structure
Desktop (1440 × 1100) with 240px fixed-width sidebar and 1200px content region. Background #080D19. Main canvas padding 28. Grid 12 columns; gutter 16.
Sidebar: wordmark KALMAN LAB, nav Overview, Triple Barrier, Strategy Comparison, Regime Analytics, Historical Replay, CI Monitor.
Top bar: title Triple Barrier Research, subtitle R5.1 / R5.2, compact tags [READ ONLY] [Historical], right status capsule CI PASS / CI RUNNING / ERROR / NOT AVAILABLE and source freshness timestamp.
KPI ribbon: four cards (Return, MDD, Win rate, Trades), and persistent secondary annotation Event-study proxy / Not a capital-constrained portfolio.
Strategy tab bar R5.1 / R5.2. Main comparison grid: baseline, fixed TP 3% SL 3%, ATR-scaled TP/SL; show fees, exposure, concurrent positions and data completeness as separate quality metrics.
One stacked horizontal region chart by Regime: counts + return + win rate; make data table accessible without needing hover.
Historical Replay table: 3 candidates / 8 fold results. Header with x/24 rows revealed, last visible event, 10-second replay countdown and separate Pause replay button. Treat historical folds as frozen data snapshots, not live trading.
CI Monitor: latest run, commit SHA, run created, run result, last poll. Distinguish running tests, actual history backtests and skipped jobs.
Footnote panel: A complete result requires matched R5 signals and OHLC; no data means unavailable, not 0.

## Tokens
Typography: Inter, headings 28/34 medium and 18/24 semibold; KPIs 28/36 bold; table 12/18; body 14/22.
Colors:
- canvas #080D19
- panel #121B2C
- subtle #19243A
- hairline #24314A
- primary text #EDF3FF
- secondary text #8E9CB7
- blue accent #75AFFF
- positive #6BD5A6
- negative #EF8F95
- pending #E8C577
Radius: 16 cards; 10 controls; 999 status pill. Padding: 20 card; table rows min-height 44. Spacing scale 4/8/12/16/20/28/36.

## Components to author as EDITABLE Figma layers
1. NavItem states default/active/disabled
2. MetricCard states populated/unavailable/loading
3. StatusPill states success/running/error/unavailable
4. StrategySwitch R5.1/R5.2
5. MethodRow baseline/fixed/ATR
6. HistoricalReplayRow with provenance
7. ResultTable sortable header and empty state
8. CIEvent item with clickable URL
9. RegimeBarSeries + legend
10. DataQuality banner

## Interaction contract
- R5.1/R5.2 switches same date window and portfolio assumptions.
- Data unavailable -> typography “—”, annotated “Historical inputs not connected”; do not substitute zero.
- Every 10 seconds: fetch once; update timestamp, CI and any new published result.
- One new historic fold revealed every 10 seconds until 24/24; separate from network polling.
- Data source provenance visible for every mode. No arbitrary forecasted profits.
- Source link: https://github.com/kimtk94/Codex/tree/main/research/kalman_triple_barrier

## Responsive
Tablet 1024: sidebar collapses to icons, KPI 2×2.
Mobile 390: no sidebar; compact header, KPI 2×2, strategy tabs scroll horizontally, table horizontal scroll.

## Exit criteria
- Main dashboard is Figma editable frames, text, components; no single rasterized screenshot.
- 1440 desktop and 390 mobile created.
- Matches the live web source states accurately.
- Data and CI provenance separated, especially baseline R5.2 vs Triple Barrier calculations.
- Figma screenshot visually reviewed and node hierarchy validated.
