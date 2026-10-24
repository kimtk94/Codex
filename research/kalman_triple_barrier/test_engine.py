import importlib.util
from pathlib import Path
import pandas as pd
import pytest

spec=importlib.util.spec_from_file_location("engine",Path(__file__).with_name("engine.py"))
engine=importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

def fixture():
    dates=pd.bdate_range("2026-01-02",periods=32)
    bars=pd.DataFrame([{"symbol":"QQQ","date":day,"open":100.,"high":101.,"low":99.,"close":100.} for day in dates])
    signals=pd.DataFrame([{"signal_id":"r51_a","strategy":"R5.1","symbol":"QQQ","date":dates[17],"regime":"UP"}])
    return signals,bars

def test_time_exit_and_volatility():
    signals,bars=fixture()
    for mode in ("fixed","vol"):
        df=engine.simulate(signals,bars,mode,.03,.03,4,0,14,.02)
        assert len(df)==1
        assert df.iloc[0].exit_reason=="TIME"
        assert df.iloc[0].net_return==0

def test_ambiguous_bar_uses_stop():
    signals,bars=fixture()
    d=signals.iloc[0]["date"]
    next_idx=bars.index[bars.date.eq(d)][0]+1
    bars.loc[next_idx,["high","low"]]=[104.,96.]
    df=engine.simulate(signals,bars,"fixed",.03,.03,4,0,14,.02)
    assert df.iloc[0].exit_reason=="SL"
    assert df.iloc[0].net_return==pytest.approx(-.03)

def test_gap_stop_worse_than_barrier():
    signals,bars=fixture()
    d=signals.iloc[0]["date"]
    next_idx=bars.index[bars.date.eq(d)][0]+1
    bars.loc[next_idx+1,["open","high","low","close"]]=[95.,98.,94.,97.]
    df=engine.simulate(signals,bars,"fixed",.03,.03,4,0,14,.02)
    assert df.iloc[0].exit_reason=="SL_GAP"
    assert df.iloc[0].net_return==pytest.approx(-.05)

def test_empty_stats():
    assert engine.stats(pd.DataFrame())=={"trades":0}
