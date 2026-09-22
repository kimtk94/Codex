import importlib.util
from pathlib import Path

P=Path(__file__).resolve().parents[1]/"research"/"r8_sec_corporate_events.py"
spec=importlib.util.spec_from_file_location("r8sec",P)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_symbol_normalization_handles_share_class_punctuation():
    assert m.norm_symbol("BRK.B")==m.norm_symbol("BRK-B")=="BRKB"

def test_item_bucket_mapping():
    items=m.split_items("2.02, 7.01, 9.01")
    assert items==["2.02","7.01","9.01"]
    assert m.event_buckets(items)==["EARNINGS_RESULTS","FINANCIAL_EXHIBITS","REG_FD"]

def test_archive_url_contract():
    u=m.archive_primary_url("0000320193","0000320193-26-000001","aapl-8k.htm")
    assert u=="https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/aapl-8k.htm"

def test_acceptance_missing_is_not_imputed():
    assert m.parse_acceptance(None) is None
    assert m.parse_acceptance("") is None
