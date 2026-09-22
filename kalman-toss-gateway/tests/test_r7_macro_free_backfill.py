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


def test_parse_archive_cpi():
    text = (
        "The Consumer Price Index for All Urban Consumers (CPI-U) increased 0.4 percent "
        "on a seasonally adjusted basis in August. "
        "The index for all items less food and energy rose 0.3 percent in August."
    )
    got=m.parse_archive_actuals("CPI",text)
    assert got["CPI_HEADLINE_MOM"]==0.4
    assert got["CORE_CPI_MOM"]==0.3


def test_parse_archive_employment_positive_and_parenthetical():
    text = (
        "Total nonfarm payroll employment increased by 162,000 in August, and the "
        "unemployment rate was unchanged at 4.1 percent. "
        "In August, average hourly earnings for all employees on private nonfarm payrolls "
        "rose by 12 cents, or 0.3 percent, to $37.50."
    )
    got=m.parse_archive_actuals("EMPLOYMENT",text)
    assert got["NFP"]==162.0
    assert got["UNEMPLOYMENT_RATE"]==4.1
    assert got["AVERAGE_HOURLY_EARNINGS_MOM"]==0.3

    text2="Both total nonfarm payroll employment (-23,000) and the unemployment rate (4.1 percent) changed little in July."
    got2=m.parse_archive_actuals("EMPLOYMENT",text2)
    assert got2["NFP"]==-23.0
    assert got2["UNEMPLOYMENT_RATE"]==4.1


def test_parse_archive_ppi_and_jolts():
    ppi=m.parse_archive_actuals("PPI","The Producer Price Index for final demand fell 0.3 percent in June.")
    assert ppi["PPI_MOM"]==-0.3
    jolts=m.parse_archive_actuals("JOLTS","The number of job openings increased to 7.6 million in April.")
    assert jolts["JOLTS_OPENINGS"]==7600.0


def test_archive_url_uses_release_date_et():
    e={"family":"CPI","release_at":"2026-09-11T12:30:00+00:00"}
    assert m.archive_url(e).endswith("/cpi_09112026.htm")


def test_employment_release_pattern_excludes_veterans():
    pat=m.RELEASE_PATTERNS["EMPLOYMENT"]
    assert pat.search("Employment Situation for February 2020")
    assert not pat.search("Employment Situation of Veterans for Annual 2019")


def test_parse_archive_jolts_historical_phrasings():
    cases={
        "Job openings decreased to 6.2 million on the last business day of March.":6200.0,
        "The number of job openings reached a series high of 8.1 million on the last business day of March.":8100.0,
        "The number of job openings increased to a series high of 10.1 million on the last business day of June.":10100.0,
        "The number of job openings was little changed at 9.2 million on the last business day of May.":9200.0,
    }
    for text,expected in cases.items():
        got=m.parse_archive_actuals("JOLTS",text)
        assert got["JOLTS_OPENINGS"]==expected


def test_nfp_archive_unit_is_thousands():
    up=m.parse_archive_actuals(
        "EMPLOYMENT",
        "Total nonfarm payroll employment increased by 250,000 in August."
    )
    down=m.parse_archive_actuals(
        "EMPLOYMENT",
        "Total nonfarm payroll employment declined by 50,000 in August."
    )
    paren=m.parse_archive_actuals(
        "EMPLOYMENT",
        "Both total nonfarm payroll employment (-23,000) and the unemployment rate (4.1 percent) changed little in July."
    )
    assert up["NFP"]==250.0
    assert down["NFP"]==-50.0
    assert paren["NFP"]==-23.0
