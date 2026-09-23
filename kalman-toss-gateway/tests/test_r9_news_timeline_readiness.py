import importlib.util
from pathlib import Path
import pandas as pd

P=Path(__file__).resolve().parents[1]/"research"/"r9_news_timeline_readiness.py"
spec=importlib.util.spec_from_file_location("r9timeline",P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def test_alias_contract():
    assert m.query_alias("AMAZON COM INC","AMZN")=="Amazon"
    assert m.query_alias("JPMORGAN CHASE & CO","JPM")=="JPMorgan Chase"
    assert m.query_alias("ExxonMobil Holdings Corporation","XOM")=="ExxonMobil"

def test_parse_timelinevolraw():
    payload={
        "timeline":[
            {
                "series":"Volume Intensity",
                "data":[
                    {"date":"20260801T000000Z","value":12,"norm":1200},
                    {"date":"20260802T000000Z","value":6,"norm":1000},
                ],
            }
        ]
    }
    x=m.parse_timeline(payload,"NVDA","NVIDIA CORP","NVIDIA")
    assert len(x)==2
    assert x.loc[0,"matched_articles"]==12
    assert x.loc[0,"monitored_articles"]==1200
    assert abs(x.loc[0,"coverage_share"]-0.01)<1e-12

def test_current_utc_day_is_not_required_by_historical_end():
    end=pd.Timestamp("2026-09-02T00:00:00Z")
    signal=pd.Timestamp("2026-09-02T13:30:00Z")
    assert end<=signal.floor("D")
