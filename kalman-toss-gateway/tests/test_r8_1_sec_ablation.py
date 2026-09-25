import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

P=Path(__file__).resolve().parents[1]/"research"/"r8_1_sec_ablation.py"
spec=importlib.util.spec_from_file_location("r81",P)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_sec_contract_is_frozen():
    assert m.SEC_HALF_LIFE_HOURS==48.0
    assert m.SEC_MAX_AGE_HOURS==120.0
    assert m.SEC_PUBLICATION_EMBARGO_MINUTES==5
    assert "FINANCIAL_EXHIBITS" not in m.SEC_BUCKET_FEATURE
    assert m.CHALLENGER=="R8C1_SEC_CORPORATE_EVENT"

def test_sec_feature_is_not_available_before_acceptance():
    df=pd.DataFrame({
        "timestamp":pd.to_datetime(["2026-01-02T13:30:00Z"]),
        "symbol":["AAPL"],
    })
    ev=pd.DataFrame([{
        "symbol":"AAPL",
        "acceptance_at":pd.Timestamp("2026-01-02T15:00:00Z"),
        "semantic_event":True,
        "event_buckets":["EARNINGS_RESULTS"],
    }])
    got,_=m.attach_sec_features(df,ev)
    assert got["sec_any_decay_48h"].iloc[0]==0.0
    assert got["sec_earnings_results_decay_48h"].iloc[0]==0.0

def test_sec_feature_enters_at_bar_end_cutoff():
    df=pd.DataFrame({
        "timestamp":pd.to_datetime(["2026-01-02T13:30:00Z"]),
        "symbol":["AAPL"],
    })
    ev=pd.DataFrame([{
        "symbol":"AAPL",
        "acceptance_at":pd.Timestamp("2026-01-02T14:00:00Z"),
        "semantic_event":True,
        "event_buckets":["EARNINGS_RESULTS"],
    }])
    got,_=m.attach_sec_features(df,ev)
    assert got["sec_any_decay_48h"].iloc[0] > 0
    assert got["sec_earnings_results_decay_48h"].iloc[0] > 0

def test_financial_exhibits_only_is_not_semantic():
    rows=[{
        "symbol":"AAPL",
        "acceptance_at":"2026-01-02T14:00:00Z",
        "event_buckets":["FINANCIAL_EXHIBITS"],
    }]
    # Mirror load_sec_events semantic policy without file IO.
    semantic=bool([b for b in rows[0]["event_buckets"] if b in m.SEC_BUCKET_FEATURE])
    assert semantic is False

def test_decay_zero_after_120h():
    x=m._decay(np.array([0.0,48.0,120.0,120.0001]))
    assert x[0]==1.0
    assert abs(x[1]-0.5)<1e-12
    assert x[2] > 0
    assert x[3]==0.0


def test_five_minute_embargo_blocks_same_boundary():
    accepted=pd.Timestamp("2026-01-02T14:30:00Z")
    available=accepted+pd.to_timedelta(m.SEC_PUBLICATION_EMBARGO_MINUTES,unit="m")
    signal_as_of=pd.Timestamp("2026-01-02T14:30:00Z")
    assert available > signal_as_of
