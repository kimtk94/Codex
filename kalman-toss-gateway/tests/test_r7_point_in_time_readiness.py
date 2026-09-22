import importlib.util
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "research" / "r7_point_in_time_readiness.py"
spec = importlib.util.spec_from_file_location("r7", P)
r7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r7)

def test_years_between_none_is_zero():
    assert r7.years_between(None, None) == 0.0
