# Kalman quality gate: offline-only
Run `python3 -m unittest -v test_quality_gate.py` and `python3 quality_gate.py --at 2026-10-14T11:35:00Z`.
Input JSON is a manually audited snapshot, not a live feed. No broker, database, or deployment writes occur. Results are observational and must never automatically control trading.
