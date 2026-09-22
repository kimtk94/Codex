import importlib.util
from pathlib import Path

P=Path(__file__).resolve().parents[1]/"research"/"r7_macro_free_backfill.py"
spec=importlib.util.spec_from_file_location("r7free",P)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def test_pct():
    assert round(m.pct(101,100),6)==1.0

def test_reference_month():
    assert m.parse_reference_month("Consumer Price Index for August 2026")== (2026,8)

def test_series_contract():
    assert m.SERIES["CPI_HEADLINE_INDEX"]=="CUSR0000SA0"
    assert m.SERIES["CORE_CPI_INDEX"]=="CUSR0000SA0L1E"
    assert m.SERIES["NFP_LEVEL"]=="CES0000000001"
    assert m.SERIES["UNEMPLOYMENT_RATE"]=="LNS14000000"
    assert m.SERIES["AHE_LEVEL"]=="CES0500000003"
    assert m.SERIES["PPI_FINAL_DEMAND_INDEX"]=="WPSFD4"
    assert m.SERIES["JOLTS_OPENINGS"]=="JTS000000000000000JOL"


def test_parse_bls_value_missing_markers():
    for x in ["-", ".", "", "NA", "N/A", None]:
        assert m.parse_bls_value(x) is None


def test_parse_bls_value_numeric_and_comma():
    assert m.parse_bls_value("123.4") == 123.4
    assert m.parse_bls_value("1,234") == 1234.0
    assert m.parse_bls_value("not-a-number") is None
