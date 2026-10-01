import importlib.util
from pathlib import Path
import pandas as pd

P=Path(__file__).resolve().parents[1]/"research"/"r7_1_macro_ablation.py"
spec=importlib.util.spec_from_file_location("r71",P)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_relative_target_contract():
    x=pd.DataFrame({
        "timestamp":pd.to_datetime(["2026-01-01T00:00:00Z"]*3),
        "fwd_ret_4b":[0.01,0.02,-0.01],
    })
    med=x.groupby("timestamp")["fwd_ret_4b"].transform("median")
    got=x["fwd_ret_4b"]-med
    assert got.tolist()==[0.0,0.01,-0.02]

def test_macro_features_are_global_per_timestamp_and_pit():
    df=pd.DataFrame({
        "timestamp":pd.to_datetime([
            "2026-01-02T13:30:00Z","2026-01-02T13:30:00Z",
            "2026-01-02T14:30:00Z","2026-01-02T14:30:00Z",
        ]),
        "symbol":["A","B","A","B"],
    })
    states=pd.DataFrame({
        "release_at":pd.to_datetime(["2026-01-02T12:30:00Z"]),
        "available_at":pd.to_datetime(["2026-01-02T14:30:00Z"]),
        "family":["CPI"],
        "actual_delta_pressure":[1.0],
        "session_reaction_1h":[0.01],
    })
    got,audit=m.attach_macro_features(df,states)
    first=got.loc[got["timestamp"]==pd.Timestamp("2026-01-02T13:30:00Z")]
    assert first["m_event_decay_24h"].nunique()==1
    assert first["m_event_decay_24h"].iloc[0] > 0
    assert audit["signal_as_of_contract"]=="timestamp + 60 minutes"

def test_macro_not_available_before_reaction_bar_end():
    df=pd.DataFrame({
        "timestamp":pd.to_datetime(["2026-01-02T12:30:00Z"]),
        "symbol":["A"],
    })
    states=pd.DataFrame({
        "release_at":pd.to_datetime(["2026-01-02T12:30:00Z"]),
        "available_at":pd.to_datetime(["2026-01-02T14:30:00Z"]),
        "family":["CPI"],
        "actual_delta_pressure":[1.0],
        "session_reaction_1h":[0.01],
    })
    got,_=m.attach_macro_features(df,states)
    assert got["m_event_decay_24h"].iloc[0]==0.0

def test_nfp_scale_contract_is_thousands():
    assert m.INDICATOR_SCALE["NFP"]==(50.0,1.0)
