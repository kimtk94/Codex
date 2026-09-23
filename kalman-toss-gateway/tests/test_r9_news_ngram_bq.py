import importlib.util
from pathlib import Path
import json
import pandas as pd

P=Path(__file__).resolve().parents[1]/"research"/"r9_news_ngram_bq.py"
spec=importlib.util.spec_from_file_location("r9ng",P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def test_alias_overrides():
    assert m.OVERRIDES["AAPL"]=="Apple Inc"
    assert m.OVERRIDES["JPM"]=="JPMorgan Chase"
    assert m.OVERRIDES["XOM"]=="ExxonMobil"

def test_default_alias_strips_legal_suffix():
    assert m.default_alias("MICROSOFT CORP")=="MICROSOFT"
    assert m.default_alias("Walmart Inc.")=="Walmart"

def test_sql_is_bounded_and_exact_ngram():
    reg=pd.DataFrame([
        {"symbol":"MSFT","alias_lower":"microsoft","ngram_order":1,"status":"SUPPORTED"},
        {"symbol":"AAPL","alias_lower":"apple inc","ngram_order":2,"status":"SUPPORTED"},
    ])
    sql=m.build_sql(reg)
    assert "web_1grams" in sql
    assert "web_2grams" in sql
    assert "DATE >= 20230701000000" in sql
    assert "DATE < 20260902000000" in sql
    assert "LANG = 'ENGLISH'" in sql
    assert "LOWER(g.NGRAM) = a.alias_lower" in sql
    assert "REGEXP" not in sql

def test_three_word_alias_requires_override():
    events=[
        {"symbol":"ZZZ","company_name":"Bank of America Corp"},
    ]
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"events.json"
        p.write_text(json.dumps(events))
        r=m.load_registry(p)
        assert r.iloc[0]["status"]=="NEEDS_OVERRIDE"


def test_frozen_public_name_contractions():
    expected={
        "AMAT":"Applied Materials",
        "AMD":"Advanced Micro",
        "AMT":"American Tower",
        "BMY":"Bristol Myers",
        "BNY":"BNY Mellon",
        "COF":"Capital One",
        "DHR":"Danaher",
        "IBM":"IBM",
        "LLY":"Eli Lilly",
        "PG":"Procter Gamble",
        "PM":"Philip Morris",
        "QCOM":"Qualcomm",
        "TMO":"Thermo Fisher",
        "UPS":"UPS",
        "USB":"US Bancorp",
        "WFC":"Wells Fargo",
        "BAC":"BofA",
        "JNJ":"J&J",
        "T":"AT&T",
    }
    for k,v in expected.items():
        assert m.OVERRIDES[k]==v



def test_final_public_shorthands_fit_ngram_contract():
    for symbol in ("BAC","JNJ","T"):
        alias=m.OVERRIDES[symbol]
        assert 1 <= len(alias.split()) <= 2
