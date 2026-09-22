import importlib.util
from pathlib import Path
import pandas as pd

P=Path(__file__).resolve().parents[1]/"research"/"r9_news_pit_readiness.py"
spec=importlib.util.spec_from_file_location("r9news",P)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_canonical_url_strips_tracking_and_fragment():
    u=m.canonical_url("HTTPS://Example.COM/a?utm_source=x&id=3#frag")
    assert u=="https://example.com/a?id=3"

def test_parse_seen_contract():
    t=m.parse_seen("20260826T123000Z")
    assert t==pd.Timestamp("2026-08-26T12:30:00Z")

def test_alias_is_company_name_not_ticker():
    assert m.query_alias("MICROSOFT CORP","MSFT")=="Microsoft"

def test_article_id_is_symbol_scoped():
    u="https://example.com/x"
    assert m.article_id("GOOG",u)!=m.article_id("GOOGL",u)

def test_smoke_symbol_contract_is_deterministic():
    reg=pd.DataFrame({"symbol":["AAPL","MSFT","NVDA","AMZN","META","GOOG","JPM","XOM","WMT","UNH"]})
    assert m.select_smoke_symbols(reg)==["AAPL","MSFT","NVDA","AMZN","META","GOOG","JPM","XOM","WMT","UNH"]


def test_public_alias_overrides_avoid_legal_suffix_noise():
    assert m.query_alias("AMAZON COM INC","AMZN")=="Amazon"
    assert m.query_alias("JPMORGAN CHASE & CO","JPM")=="JPMorgan Chase"
    assert m.query_alias("ExxonMobil Holdings Corporation","XOM")=="ExxonMobil"


class _FakeClient:
    max_retries=0
    def __init__(self):
        self.calls=[]
    def search(self,alias,start,end,maxrecords=250):
        self.calls.append((pd.Timestamp(start),pd.Timestamp(end)))
        hours=(pd.Timestamp(end)-pd.Timestamp(start)).total_seconds()/3600.0
        n=250 if hours>24 else 100
        return {"articles":[{"url":f"https://example.com/{len(self.calls)}/{i}","seendate":"20260801T000000Z"} for i in range(n)]},{"cache_hit":False,"attempts":1}

def test_saturated_window_splits_until_terminal_not_saturated():
    client=_FakeClient()
    rows,audit=m.collect_window(
        client,
        "NVIDIA",
        pd.Timestamp("2026-08-01T00:00:00Z"),
        pd.Timestamp("2026-08-03T00:00:00Z"),
        maxrecords=250,
        min_window_hours=24,
    )
    terminal=[x for x in audit if x["terminal"]]
    assert len(client.calls)>1
    assert len(terminal)>=2
    assert all(x["saturated"] is False for x in terminal)
    assert len(rows)>=200

def test_query_alias_overrides_remain_public_names():
    assert m.query_alias("AMAZON COM INC","AMZN")=="Amazon"
    assert m.query_alias("JPMORGAN CHASE & CO","JPM")=="JPMorgan Chase"
    assert m.query_alias("ExxonMobil Holdings Corporation","XOM")=="ExxonMobil"
