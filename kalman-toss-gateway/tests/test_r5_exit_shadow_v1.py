import importlib.util
from pathlib import Path
import pandas as pd

P=Path(__file__).resolve().parents[1]/"research"/"r5_exit_shadow_v1.py"
spec=importlib.util.spec_from_file_location("r5exit",P)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_frozen_boundary_and_horizons():
    assert m.START==pd.Timestamp("2026-09-22T10:45:00Z")
    assert m.HORIZONS==(2,4,6,8)

def test_ids_are_deterministic():
    t=pd.Timestamp("2026-09-22T13:30:00Z")
    assert m.signal_id("AAPL",t)==m.signal_id("AAPL",t)
    assert m.outcome_id(m.signal_id("AAPL",t),4)==m.outcome_id(m.signal_id("AAPL",t),4)

def test_status_does_not_select_horizon_early():
    s=pd.DataFrame([{
        "signal_id":"x","mapping_status":"EXACT_CANONICAL_MATCH"
    }])
    o=pd.DataFrame(columns=["horizon_buckets","as_of","net10_return"])
    st=m.status(s,o)
    assert st["review_rule"]=="NO_HORIZON_SELECTION_BEFORE_MINIMUM_REVIEW_GATE"
    assert st["live_exit_changed"] is False
