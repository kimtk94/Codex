from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd
import yaml


DEFAULT_ROOT = Path("/srv/is-analysis")
DEFAULT_PROJECT = DEFAULT_ROOT / "IS_Analysis_V3"
DEFAULT_DATA = DEFAULT_ROOT / "data" / "multi_organ_aging"
DEFAULT_RESULTS = DEFAULT_ROOT / "results" / "multi_organ_aging"


def mkdirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def load_yaml(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_json(obj, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def read_table_auto(path: str | Path, nrows: Optional[int] = None) -> pd.DataFrame:
    path = Path(path)
    suffixes = "".join(path.suffixes).lower()
    if suffixes.endswith(".parquet"):
        return pd.read_parquet(path)
    if suffixes.endswith(".xlsx") or suffixes.endswith(".xls"):
        return pd.read_excel(path, nrows=nrows)
    if suffixes.endswith(".csv") or suffixes.endswith(".csv.gz"):
        return pd.read_csv(path, nrows=nrows, low_memory=False)
    return pd.read_csv(path, sep=None, engine="python", nrows=nrows, low_memory=False)


def normalize_col(x: str) -> str:
    x = str(x).strip().upper()
    x = re.sub(r"[^A-Z0-9]+", "_", x)
    return re.sub(r"_+", "_", x).strip("_")


def find_first_column(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    norm_to_raw = {normalize_col(c): c for c in columns}
    for c in candidates:
        key = normalize_col(c)
        if key in norm_to_raw:
            return norm_to_raw[key]
    return None


def match_patterns(columns: Sequence[str], patterns: Sequence[str]) -> List[str]:
    out = []
    for c in columns:
        nc = normalize_col(c)
        if any(re.search(p, nc, flags=re.I) for p in patterns):
            out.append(c)
    return sorted(set(out))


def numeric_coerce(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce")
    x = (
        s.astype(str)
        .str.strip()
        .replace({"": np.nan, ".": np.nan, "NA": np.nan, "N/A": np.nan, "nan": np.nan})
    )
    return pd.to_numeric(x, errors="coerce")


def robust_z(s: pd.Series, ref: Optional[pd.Series] = None) -> pd.Series:
    r = s if ref is None else ref
    r = pd.to_numeric(r, errors="coerce")
    med = r.median()
    mad = (r - med).abs().median()
    scale = 1.4826 * mad
    if not np.isfinite(scale) or scale <= 1e-12:
        scale = r.std(ddof=0)
    if not np.isfinite(scale) or scale <= 1e-12:
        scale = 1.0
    return (pd.to_numeric(s, errors="coerce") - med) / scale


def bh_fdr(pvals: Iterable[float]) -> np.ndarray:
    p = np.asarray(list(pvals), dtype=float)
    n = len(p)
    order = np.argsort(np.where(np.isfinite(p), p, np.inf))
    q = np.full(n, np.nan)
    finite = np.isfinite(p)
    m = finite.sum()
    if m == 0:
        return q
    ranks = np.arange(1, m + 1)
    ordered = p[order[:m]]
    vals = ordered * m / ranks
    vals = np.minimum.accumulate(vals[::-1])[::-1]
    q[order[:m]] = np.minimum(vals, 1.0)
    return q


def slope_ols(x: pd.Series, y: pd.Series) -> float:
    d = pd.DataFrame({
        "x": pd.to_numeric(x, errors="coerce"),
        "y": pd.to_numeric(y, errors="coerce"),
    }).dropna()
    if len(d) < 2 or d["x"].nunique() < 2:
        return np.nan
    return float(np.polyfit(d["x"].to_numpy(), d["y"].to_numpy(), 1)[0])
