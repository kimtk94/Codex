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


def test_passive_sec_tag_uses_embargo_and_120h_window():
    idx={
        "AAPL":[
            {
                "available_at":pd.Timestamp("2026-09-22T14:35:00Z"),
                "buckets":["EARNINGS_RESULTS"],
            }
        ]
    }
    before=m.sec_tag("AAPL",pd.Timestamp("2026-09-22T14:30:00Z"),idx)
    after=m.sec_tag("AAPL",pd.Timestamp("2026-09-22T15:30:00Z"),idx)
    assert before["sec_active_120h"] is False
    assert after["sec_active_120h"] is True
    assert after["sec_latest_buckets_csv"]=="EARNINGS_RESULTS"
    assert 0 < after["sec_any_decay_48h"] <= 1


def test_passive_sec_tag_does_not_change_live_flags():
    s=pd.DataFrame([{
        "signal_id":"x",
        "mapping_status":"EXACT_CANONICAL_MATCH",
        "sec_active_120h":True,
    }])
    o=pd.DataFrame(columns=["horizon_buckets","as_of","net10_return"])
    st=m.status(s,o)
    assert st["production_changed"] is False
    assert st["live_exit_changed"] is False
    assert st["sec_tag_contract"]["passive_only"] is True
    assert st["sec_tag_contract"]["live_sizing_changed"] is False
