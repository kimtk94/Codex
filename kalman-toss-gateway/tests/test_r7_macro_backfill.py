import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "research" / "r7_macro_backfill.py"
spec = importlib.util.spec_from_file_location("r7m", P)
r7m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r7m)


def test_chunk_ranges_are_contiguous():
    xs = r7m.chunk_ranges(date(2026, 1, 1), date(2026, 1, 10), 4)
    assert xs == [
        (date(2026, 1, 1), date(2026, 1, 4)),
        (date(2026, 1, 5), date(2026, 1, 8)),
        (date(2026, 1, 9), date(2026, 1, 10)),
    ]


def test_audit_event_time_ratio():
    utc = timezone.utc
    rows = [
        {
            "indicator_key": "CPI_HEADLINE_MOM",
            "release_at": datetime(2026, 1, 1, 13, 30, tzinfo=utc),
            "available_at": datetime(2026, 1, 1, 13, 35, tzinfo=utc),
            "actual": 0.3,
            "consensus": 0.2,
            "time_quality": "PROVIDER_RELEASE_TS",
        },
        {
            "indicator_key": "NFP",
            "release_at": datetime(2026, 1, 2, 13, 30, tzinfo=utc),
            "available_at": datetime(2026, 1, 2, 16, 30, tzinfo=utc),
            "actual": 150,
            "consensus": 140,
            "time_quality": "PROVIDER_RELEASE_TS",
        },
    ]
    a = r7m.audit(rows)
    assert a["rows"] == 2
    assert a["consensus_ratio"] == 1.0
    assert a["event_time_usable_ratio_120m"] == 0.5
