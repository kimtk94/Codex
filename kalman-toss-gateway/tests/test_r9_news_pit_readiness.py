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
    assert m.query_alias("MICROSOFT CORP")=="MICROSOFT Corp"

def test_article_id_is_symbol_scoped():
    u="https://example.com/x"
    assert m.article_id("GOOG",u)!=m.article_id("GOOGL",u)

def test_smoke_symbol_contract_is_deterministic():
    reg=pd.DataFrame({"symbol":["AAPL","MSFT","NVDA","AMZN","META","GOOG","JPM","XOM","WMT","UNH"]})
    assert m.select_smoke_symbols(reg)==["AAPL","MSFT","NVDA","AMZN","META","GOOG","JPM","XOM","WMT","UNH"]
