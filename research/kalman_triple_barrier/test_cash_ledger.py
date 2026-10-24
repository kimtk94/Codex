import importlib.util
from pathlib import Path
import pandas as pd
import pytest
p=Path(__file__).with_name("cash_ledger.py")
spec=importlib.util.spec_from_file_location("cash_ledger",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_constant_market_fees_and_cap():
    t=pd.date_range("2026-01-05 14:30",periods=30,freq="min",tz="UTC")
    df=pd.DataFrame({"symbol":"QQQ","timestamp":t,"open":100.,"high":100.,"low":100.,"close":100.})
    x=m.evaluate(df,horizon=10,spacing=1,legs=3,capital=1000,allocation=.3,fee_bps=5)
    assert x["nonoverlap_windows"]==3
    assert x["leg_fills"]==9
    assert x["return_pct"]<0
    assert x["max_marked_exposure_pct"]<=30.1
    assert x["intrabar_marked_mdd_pct"]<=0

def test_gap_is_not_crossed():
    t=pd.date_range("2026-01-05 14:30",periods=12,freq="min",tz="UTC")
    df=pd.DataFrame({"symbol":"QQQ","timestamp":t,"open":100.,"high":100.,"low":100.,"close":100.})
    df.loc[6:,"timestamp"]=df.loc[6:,"timestamp"]+pd.Timedelta(hours=1)
    x=m.evaluate(df,horizon=10,spacing=1,legs=2)
    assert x["nonoverlap_windows"]==0

def test_multiple_assets_explicitly_rejected():
    t=pd.date_range("2026-01-05 14:30",periods=10,freq="min",tz="UTC")
    df=pd.DataFrame({"symbol":["QQQ"]*5+["QLD"]*5,"timestamp":t,"open":100.,"high":100.,"low":100.,"close":100.})
    with pytest.raises(ValueError,match="single-symbol"):m.evaluate(df,5,1,2)
