# Grid Regime Gap Fix — Real-data Regression

- Prior successful run: https://github.com/kimtk94/Codex/actions/runs/39124502619
- Revised successful run: https://github.com/kimtk94/Codex/actions/runs/39126120410
- Revised artifact ID: 12136585962
- Run #8 read-only verification: PASS
- All eight annual 2025 return and MDD values are identical across runs at reported four-decimal precision.
- Result: the corrective gap reset change had no observed impact on these aggregate performance metrics.
- This does NOT establish that all order state transitions are correct. The synthetic invariant tests passed; an explicit real-data gap event/count diagnostic is outstanding.
- Strategy decision: reject simple SMA20/SMA60 filters for profitability in 2025; retain baseline as a comparison only, not a profitable validated strategy.
- Follow-up: examine price exposure and gap-event counts; prioritize execution-aware risk control. Keep SSH backtests manual-only, preserve LIVE isolation.
