import importlib.util
from pathlib import Path
import pandas as pd
import pytest

spec=importlib.util.spec_from_file_location("parity",Path(__file__).with_name("intraday_parity.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def make(path,volume=100,timestamp="2026-10-23T13:31:00+00:00"):
    pd.DataFrame([{"timestamp":timestamp,"open":100.0,"high":101.0,"low":99.0,"close":100.5,"volume":volume}]).to_csv(path,index=False)

def test_exact_prices_different_volume(tmp_path):
    a,b=tmp_path/"a.csv",tmp_path/"b.csv"
    make(a,100);make(b,200)
    report=m.compare(a,b)
    assert report["common_minutes"]==1
    assert report["metrics"]["close"]["exact_match_count"]==1
    assert report["metrics"]["volume"]["max_abs_gap_pct"]==50.0

def test_no_utc_offset_rejected(tmp_path):
    a=tmp_path/"a.csv";make(a,timestamp="2026-10-23 09:31:00")
    with pytest.raises(ValueError,match="EXPLICIT_UTC_OFFSET"):m.load(a)

def test_nonoverlap_not_comparable(tmp_path):
    a,b=tmp_path/"a.csv",tmp_path/"b.csv"
    make(a);make(b,timestamp="2026-10-23T13:32:00+00:00")
    assert m.compare(a,b)["status"]=="NO_OVERLAP"
