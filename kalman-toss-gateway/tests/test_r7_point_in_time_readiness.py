import importlib.util
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "research" / "r7_point_in_time_readiness.py"
spec = importlib.util.spec_from_file_location("r7", P)
r7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r7)

def test_years_between_none_is_zero():
    assert r7.years_between(None, None) == 0.0


def test_years_between_iso_strings():
    y = r7.years_between("2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    assert 0.99 < y < 1.01


def test_snapshot_exists():
    assert r7.DEFAULT_SNAPSHOT.exists()
