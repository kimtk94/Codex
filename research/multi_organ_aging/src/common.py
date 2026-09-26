from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


def load_config(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def norm_name(value: str) -> str:
    s = str(value).strip().lower()
    s = re.sub(r"[^a-z0-9가-힣]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_")


def infer_sep(path: str | Path) -> str:
    name = str(path).lower()
    return "," if ".csv" in name else "\t"


def read_table(path: str | Path, nrows: int | None = None) -> pd.DataFrame:
    p = Path(path)
    name = p.name.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(p, nrows=nrows)
    return pd.read_csv(
        p,
        sep=infer_sep(p),
        compression="infer",
        nrows=nrows,
        low_memory=False,
    )


def write_table(df: pd.DataFrame, path: str | Path) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    name = p.name.lower()
    if name.endswith(".parquet"):
        df.to_parquet(p, index=False)
    elif ".csv" in name:
        df.to_csv(p, index=False, compression="infer")
    else:
        df.to_csv(p, sep="\t", index=False, compression="infer")


def list_input_files(input_dir: str | Path, globs: Sequence[str]) -> list[Path]:
    root = Path(input_dir)
    scan_roots = [root]

    shared = root / "shared_source"
    if shared.exists():
        try:
            scan_roots.append(shared.resolve())
        except OSError:
            scan_roots.append(shared)

    found: list[Path] = []
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for pattern in globs:
            found.extend(scan_root.glob(pattern))
            found.extend(scan_root.glob(f"*/{pattern}"))

    unique = {p.resolve() for p in found if p.is_file()}
    return sorted(unique)


def detect_wave(path: str | Path, wave_order: dict[str, int]) -> str:
    n = norm_name(Path(path).stem.replace(".tsv", "").replace(".csv", ""))
    ranked = sorted(wave_order, key=lambda k: len(norm_name(k)), reverse=True)
    for key in ranked:
        if norm_name(key) in n:
            return key
    return n


def resolve_column(columns: Iterable[str], aliases: Sequence[str]) -> str | None:
    columns = list(columns)
    normalized = {norm_name(c): c for c in columns}
    for a in aliases:
        na = norm_name(a)
        if na in normalized:
            return normalized[na]
    for a in aliases:
        na = norm_name(a)
        if len(na) < 3:
            continue
        candidates = [
            original
            for nc, original in normalized.items()
            if nc.startswith(na + "_") or nc.endswith("_" + na)
        ]
        if len(candidates) == 1:
            return candidates[0]
    return None


def resolve_concepts(columns: Iterable[str], concepts: dict[str, Sequence[str]]) -> dict[str, str | None]:
    return {k: resolve_column(columns, aliases) for k, aliases in concepts.items()}


def to_numeric(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    cleaned = (
        series.astype(str)
        .str.strip()
        .replace({"": np.nan, "NA": np.nan, "N/A": np.nan, "nan": np.nan, ".": np.nan})
        .str.replace(",", "", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def normalize_sex(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().str.lower()
    out = pd.Series(np.nan, index=series.index, dtype=float)
    out[s.isin(["1", "m", "male", "남", "남자"])] = 1.0
    out[s.isin(["2", "0", "f", "female", "여", "여자"])] = 0.0
    numeric = pd.to_numeric(series, errors="coerce")
    vals = set(numeric.dropna().unique().tolist())
    if vals and vals.issubset({0, 1}):
        out = numeric.astype(float)
    elif vals and vals.issubset({1, 2}):
        out = numeric.map({1: 1.0, 2: 0.0})
    return out


def egfr_2021(creatinine_mg_dl: pd.Series, age: pd.Series, sex_male: pd.Series) -> pd.Series:
    scr = to_numeric(creatinine_mg_dl)
    age = to_numeric(age)
    male = to_numeric(sex_male)
    k = np.where(male.eq(1), 0.9, 0.7)
    alpha = np.where(male.eq(1), -0.302, -0.241)
    ratio = scr / k
    sex_factor = np.where(male.eq(1), 1.0, 1.012)
    out = (
        142.0
        * np.minimum(ratio, 1.0) ** alpha
        * np.maximum(ratio, 1.0) ** -1.200
        * 0.9938 ** age
        * sex_factor
    )
    return pd.Series(out, index=scr.index).where(scr.gt(0) & age.gt(0))


def bh_fdr(pvalues: Sequence[float]) -> np.ndarray:
    p = np.asarray(pvalues, dtype=float)
    out = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    if not ok.any():
        return out
    pv = p[ok]
    order = np.argsort(pv)
    ranked = pv[order]
    q = ranked * len(ranked) / np.arange(1, len(ranked) + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0, 1)
    tmp = np.empty_like(q)
    tmp[order] = q
    out[ok] = tmp
    return out


def zscore(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    sd = x.std(ddof=0)
    if not np.isfinite(sd) or sd <= 0:
        return pd.Series(np.nan, index=x.index)
    return (x - x.mean()) / sd


def safe_corr(a: pd.Series, b: pd.Series) -> float:
    x = pd.concat([pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")], axis=1).dropna()
    return float(x.iloc[:, 0].corr(x.iloc[:, 1])) if len(x) >= 3 else math.nan


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def json_dump(obj: dict, path: str | Path) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=str)
