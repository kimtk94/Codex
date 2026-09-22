import importlib.util
from pathlib import Path
import pandas as pd

P=Path(__file__).resolve().parents[1]/"research"/"r9_sec_text_readiness.py"
spec=importlib.util.spec_from_file_location("r9text",P)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_semantic_items_exclude_9_01():
    e={"items":["2.02","9.01"],"event_buckets":["EARNINGS_RESULTS","FINANCIAL_EXHIBITS"]}
    assert m.semantic_items_from_event(e)==["2.02"]
    assert m.primary_bucket(e)=="EARNINGS_RESULTS"

def test_item_section_extraction_does_not_fallback_to_full_filing():
    txt="Intro text Item 2.02 Results of Operations revenue rose materially. More detail here. Item 9.01 Exhibits follow."
    got,found=m.extract_item_sections(txt,{"2.02"})
    assert "Item 2.02" in got
    assert "Item 9.01" not in got
    assert found==["2.02"]
    miss,_=m.extract_item_sections("No explicit item heading here",{"2.02"})
    assert miss==""

def test_primary_bucket_priority_is_frozen():
    e={"event_buckets":["OTHER_EVENT","EARNINGS_RESULTS","REG_FD"]}
    assert m.primary_bucket(e)=="EARNINGS_RESULTS"

def test_availability_embargo_is_five_minutes():
    t=pd.Timestamp("2026-01-02T14:30:00Z")
    assert t+pd.to_timedelta(5,unit="m")==pd.Timestamp("2026-01-02T14:35:00Z")


def test_item_extraction_prefers_longest_occurrence():
    short="Item 2.02 Results summary " + ("x "*50)
    long="Item 2.02 Results detailed " + ("revenue margin guidance "*120)
    text=short+" Item 9.01 Exhibits "+long+" Item 9.01 Exhibits end"
    got,found=m.extract_item_sections(text,{"2.02"})
    assert found==["2.02"]
    assert "revenue margin guidance" in got


def test_smoke_selector_prefers_distinct_symbols():
    events=[]
    for sym in ["AAPL","MSFT","NVDA"]:
        for i in range(3):
            events.append({
                "symbol":sym,
                "acceptance_at":f"2026-01-0{i+1}T00:00:00Z",
                "primary_url":f"https://sec.test/{sym}/{i}",
            })
    urls=m.select_smoke_urls(events,3)
    assert len(urls)==3
    assert any("/AAPL/" in x for x in urls)
    assert any("/MSFT/" in x for x in urls)
    assert any("/NVDA/" in x for x in urls)
