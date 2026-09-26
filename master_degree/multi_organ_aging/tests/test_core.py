import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "src"))

from moa_common import bh_fdr, normalize_col, robust_z, slope_ols


def test_normalize_col():
    assert normalize_col("HbA1c (%)") == "HBA1C"


def test_slope_ols():
    x = pd.Series([0, 2, 4], dtype=float)
    y = pd.Series([1, 2, 3], dtype=float)
    assert abs(slope_ols(x, y) - 0.5) < 1e-9


def test_robust_z_center():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    z = robust_z(s)
    assert abs(float(z.iloc[2])) < 1e-9


def test_bh_is_monotonic_for_sorted_p():
    q = bh_fdr([0.001, 0.01, 0.2])
    assert np.all(np.isfinite(q))
    assert q[0] <= q[1] <= q[2]
