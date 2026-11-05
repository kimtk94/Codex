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


def test_xom_registrant_lineage_is_frozen():
    xs=m.CIK_LINEAGE_OVERRIDES["XOM"]
    assert xs[0]["cik"]=="0000034088"
    assert xs[0]["valid_to"]=="2026-06-30"
    assert xs[1]["cik"]=="0002115436"
    assert xs[1]["valid_from"]=="2026-07-01"


def test_mapping_window_prevents_double_count_across_successor_boundary():
    old={"valid_from":"2020-01-01","valid_to":"2026-06-30"}
    new={"valid_from":"2026-07-01","valid_to":None}
    assert m._date_in_mapping_window("2025-11-13",old)
    assert not m._date_in_mapping_window("2025-11-13",new)
    assert not m._date_in_mapping_window("2026-07-01",old)
    assert m._date_in_mapping_window("2026-07-01",new)
