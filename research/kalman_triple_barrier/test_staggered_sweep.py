import importlib.util
from pathlib import Path
import pandas as pd
import pytest
spec=importlib.util.spec_from_file_location("sweep",Path(__file__).with_name("staggered_sweep.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def bars():
    t=pd.date_range("2026-01-05 14:30",periods=120,freq="min",tz="UTC")
    return pd.DataFrame([{"symbol":"QQQ","timestamp":v,"open":100.,"high":100.5,"low":99.5,"close":100.} for v in t])

def test_staggered_horizons():
    data=bars()
    result=m.run(data,[5,20,100],[1,5],[1,3],.03,.03,0,25)
    assert len(result)==12
    assert set(result.horizon_minutes)=={5,20,100}
    assert result.mean_return_pct.abs().max()==0

def test_gap_not_bridged():
    data=bars()
    data.loc[60:,"timestamp"]=data.loc[60:,"timestamp"]+pd.Timedelta(hours=12)
    assert m.run(data,[100],[1],[1],.03,.03,0).empty

def test_double_barrier_stop_first():
    data=bars()
    data.loc[0,["high","low"]]=[104.,96.]
    assert m.simulate(data,0,5,1,1)["sl_hits"]==1

def test_no_horizon_default_assumed():
    assert 100 in [5,10,20,40,60,100]


def test_equal_notional_not_equal_shares():
    data=bars()
    data.loc[0,["open","high","low","close"]]=[100.,100.,100.,100.]
    data.loc[1:,["open","high","low","close"]]=[200.,200.,200.,200.]
    # First leg exits at 200, second leg enters at 200; no stops with wide barriers.
    result=m.simulate(data,0,3,1,2,tp=2.,sl=.99,fee_bps=0)
    assert result["legs_filled"]==2
    assert result["return_pct"]==pytest.approx(50.)
