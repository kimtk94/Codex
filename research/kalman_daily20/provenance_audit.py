#!/usr/bin/env python3
"""Daily20 P0: quantify price/feature data revision vs deterministic model drift.

Runs ONLY against immutable GitHub Actions price+feature artifacts from two
completed executions on the SAME last XNYS date. Nothing is fitted to decide
a new trading policy; no live orders or Drive journal changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import sklearn

from daily20 import load_spec, market_file, feature_file, load_bars, write_json
from train import COLUMNS, context_frame, feature_frame, model_split, model_year
from regime_challenger import fit_bear_year

VERSION = "kalman-daily20-provenance-audit-v1"
RAW_COLS = ("open", "high", "low", "close", "volume")
ABS_TOL = 1e-10
REL_TOL = 1e-10


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def value_or_null(x):
    try:
        return float(x) if np.isfinite(float(x)) else None
    except (TypeError, ValueError):
        return None


def fingerprint_feature_row(frame, date):
    row = frame.loc[pd.Timestamp(date), COLUMNS]
    if isinstance(row, pd.DataFrame):
        raise RuntimeError("DUPLICATE_ASOF_FEATURE_ROW")
    return sha_bytes(canonical([value_or_null(row[k]) for k in COLUMNS]).encode())


def training_digest(frame, year, *, bear=False):
    train, _ = model_split(frame, year)
    if bear:
        from regime_challenger import bear_gate
        train = train[bear_gate(train)]
    # Canonicalize floats to avoid parquet/pandas representation differences.
    records = {
        "dates": [str(x.date()) for x in train.index],
        "y": [bool(value > 0) for value in train["net_return"]],
        "x": [[value_or_null(x) for x in row] for row in train[COLUMNS].to_numpy()],
    }
    return sha_bytes(canonical(records).encode()), len(train)


def model_digest(fitted):
    if fitted is None:
        return None
    info = {
        "class": type(fitted[-1]).__name__,
        "params": fitted[-1].get_params(),
        "steps": [],
    }
    for step in fitted:
        attrib = {}
        for k in ("statistics_", "mean_", "scale_", "coef_", "intercept_", "classes_"):
            v = getattr(step, k, None)
            if v is not None:
                if isinstance(v, np.ndarray):
                    attrib[k] = [value_or_null(x) for x in v.flatten()]
                else:
                    attrib[k] = value_or_null(v)
        info["steps"].append(attrib)
    return sha_bytes(canonical(info).encode())


def compare_numeric_frames(old, new, symbol, kind, *, expected_date):
    """Compare SEMANTIC numeric values, ignoring parquet byte/codec differences."""
    cols = [x for x in old.columns if x in new.columns and
            pd.api.types.is_numeric_dtype(old[x]) and
            pd.api.types.is_numeric_dtype(new[x]) and
            pd.api.types.is_bool_dtype(old[x]) is False]
    common = old.index.intersection(new.index)
    missing_old = new.index.difference(old.index)
    missing_new = old.index.difference(new.index)
    if len(common) == 0:
        raise RuntimeError(f"NO_COMMON_DATES:{symbol}:{kind}")
    detail = []
    daily = {}
    same = True
    for col in cols:
        a = pd.to_numeric(old.loc[common, col], errors="coerce").to_numpy(dtype=float)
        b = pd.to_numeric(new.loc[common, col], errors="coerce").to_numpy(dtype=float)
        equal = np.isclose(a, b, rtol=REL_TOL, atol=ABS_TOL, equal_nan=True)
        mask = ~equal
        finite = np.isfinite(a) & np.isfinite(b) & (np.abs(a) > 1e-12)
        relative = np.zeros(len(a), dtype=float)
        relative[finite] = np.abs(b[finite] / a[finite] - 1.0)
        indices = np.flatnonzero(mask)
        dates = [str(common[i].date()) for i in indices]
        positive = np.isfinite(a) & np.isfinite(b) & (a > 0) & (b > 0)
        ratio = b[positive] / a[positive]
        if len(ratio):
            scale_med = float(np.median(ratio))
            residual = np.abs(ratio / scale_med - 1.0)
            scale_p95 = float(np.quantile(residual, .95))
        else:
            scale_med, scale_p95 = None, None
        for i, key in zip(indices, dates):
            daily.setdefault(key, []).append(col)
        same &= len(indices) == 0
        ix = np.flatnonzero(common == pd.Timestamp(expected_date))
        last_a = value_or_null(a[ix[0]]) if len(ix) else None
        last_b = value_or_null(b[ix[0]]) if len(ix) else None
        detail.append({
            "symbol": symbol, "kind": kind, "column": col,
            "overlap_sessions": len(common),
            "changed_sessions": len(indices),
            "first_changed_date": dates[0] if dates else None,
            "last_changed_date": dates[-1] if dates else None,
            "max_relative_delta": float(relative.max()) if len(relative) else 0.,
            "max_absolute_delta": float(np.nanmax(np.abs(b[finite] - a[finite])))
                                  if finite.any() else 0.,
            "median_right_over_left_ratio": scale_med,
            "p95_abs_residual_from_median_scale": scale_p95,
            "global_multiplicative_rescale": bool(
                len(indices) > len(common) // 3 and
                scale_p95 is not None and scale_p95 < 1e-4
            ),
            "asof_left": last_a, "asof_right": last_b,
            "asof_changed": (
                not np.isclose(last_a, last_b, rtol=REL_TOL, atol=ABS_TOL, equal_nan=True)
                if last_a is not None and last_b is not None else last_a != last_b
            ),
            "missing_from_left": len(missing_old), "missing_from_right": len(missing_new),
        })
    sessions = [{
        "symbol": symbol, "kind": kind, "date": date,
        "changed_columns": ";".join(sorted(values)),
        "changed_column_count": len(values),
    } for date, values in sorted(daily.items())]
    if len(missing_old) or len(missing_new):
        same = False
    return detail, sessions, same


def normalize_feature(path):
    df = pd.read_parquet(path)
    if "timestamp" not in df.columns:
        raise RuntimeError("FEATURE_TIMESTAMP_MISSING:" + str(path))
    df = df.copy()
    df["date"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_localize(None).dt.normalize()
    if df["date"].duplicated().any():
        raise RuntimeError("FEATURE_DUPLICATE_DATES:" + str(path))
    return df.set_index("date").sort_index()


def predict_on_frame(frame, date, family):
    year = pd.Timestamp(date).year
    if family == "BULL_LOGISTIC":
        fitted, _, fold = model_year(frame, year)
        digest, nrows = training_digest(frame, year, bear=False)
    elif family == "BEAR_LOGISTIC":
        fitted, _, fold = fit_bear_year(frame, year)
        digest, nrows = training_digest(frame, year, bear=True)
    else:
        raise ValueError(family)
    if fitted is None:
        return {
            "prediction": None, "fold_status": fold["status"], "training_rows": nrows,
            "training_hash": digest, "fitted_model_hash": None,
        }
    pred = float(fitted.predict_proba(frame.loc[[pd.Timestamp(date)], COLUMNS])[:, 1][0])
    return {
        "prediction": pred, "fold_status": fold["status"], "training_rows": nrows,
        "training_hash": digest, "fitted_model_hash": model_digest(fitted),
    }


def load_frozen_scores(path):
    if not path:
        return {}
    file = Path(path)
    if file.is_dir():
        file = file / "research/forward_shadow/journal.jsonl"
    if not file.is_file():
        raise RuntimeError("MISSING_BASELINE_FROZEN_JOURNAL")
    result = {}
    for line in file.read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("kind") == "SIGNAL":
            result[(event["signal_date"], event["symbol"])] = event["probability"]
    return result


def inspect(root, symbols, expected_date):
    for symbol in symbols:
        p = market_file(Path(root) / "market", symbol)
        f = feature_file(Path(root) / "features", symbol)
        if not p.is_file() or not f.is_file():
            raise RuntimeError("INCOMPLETE_26_SNAPSHOT:" + symbol)
        bars = load_bars(p)
        if str(bars.index.max().date()) != expected_date:
            raise RuntimeError("SNAPSHOT_SESSION_NOT_MATCHED:" + symbol)
    return True


def run(left, right, spec, out, left_id, right_id, asof, frozen=None):
    left, right, out = Path(left), Path(right), Path(out)
    names = [*spec["core"], *spec["context"]]
    if not inspect(left, names, asof) or not inspect(right, names, asof):
        raise RuntimeError("INCOMPLETE_SAME_DATE_DATA")
    last = pd.Timestamp(asof)
    price, features, revised = [], [], []
    per_symbol = {}
    context_a = context_frame(left / "market")
    context_b = context_frame(right / "market")
    baseline_original = load_frozen_scores(frozen)
    pred_rows = []
    count_changed_raw = count_changed_numeric = count_changed_features = 0

    for symbol in names:
        raw_a = market_file(left / "market", symbol)
        raw_b = market_file(right / "market", symbol)
        f_a = feature_file(left / "features", symbol)
        f_b = feature_file(right / "features", symbol)
        file_diff = (
            sha_bytes(raw_a.read_bytes()) != sha_bytes(raw_b.read_bytes()),
            sha_bytes(f_a.read_bytes()) != sha_bytes(f_b.read_bytes())
        )
        count_changed_raw += int(file_diff[0])
        count_changed_features += int(file_diff[1])
        bars_a = load_bars(raw_a)
        bars_b = load_bars(raw_b)
        p, dates, identical = compare_numeric_frames(
            bars_a, bars_b, symbol, "raw_OHLCV", expected_date=asof)
        price.extend(p)
        revised.extend(dates)
        count_changed_numeric += int(not identical)
        a = normalize_feature(f_a)
        b = normalize_feature(f_b)
        x, days, indicators_same = compare_numeric_frames(
            a, b, symbol, "technical_features", expected_date=asof)
        features.extend(x)
        revised.extend(days)
        per_symbol[symbol] = {
            "raw_parquet_sha_diff": file_diff[0],
            "indicator_parquet_sha_diff": file_diff[1],
            "raw_numeric_same": identical,
            "indicators_numeric_same": indicators_same,
        }
        if symbol not in spec["core"]:
            continue
        fa = feature_frame(symbol, left / "market", left / "features",
                           context_a, float(spec["round_trip_cost_bps"]))
        fb = feature_frame(symbol, right / "market", right / "features",
                           context_b, float(spec["round_trip_cost_bps"]))
        hash_a = fingerprint_feature_row(fa, last)
        hash_b = fingerprint_feature_row(fb, last)
        for family in ("BULL_LOGISTIC", "BEAR_LOGISTIC"):
            pa = predict_on_frame(fa, asof, family)
            pb = predict_on_frame(fb, asof, family)
            repeated = predict_on_frame(fa, asof, family)
            if (pa["prediction"] != repeated["prediction"]
                    or pa["training_hash"] != repeated["training_hash"]
                    or pa["fitted_model_hash"] != repeated["fitted_model_hash"]):
                raise RuntimeError("IDENTICAL_INPUT_REFIT_NONDETERMINISTIC:" + symbol + ":" + family)
            if not (pa["fold_status"] == pb["fold_status"]
                    or pa["prediction"] is None or pb["prediction"] is None):
                raise RuntimeError("MODEL_FOLD_MISMATCH")
            pred_a = pa["prediction"]
            pred_b = pb["prediction"]
            old_frozen = baseline_original.get((asof, symbol)) if family == "BULL_LOGISTIC" else None
            pred_rows.append({
                "symbol": symbol, "family": family, "asof_date": asof,
                "left_run_id": str(left_id), "right_run_id": str(right_id),
                "left_prediction": pred_a, "right_prediction": pred_b,
                "prediction_delta_pp": (
                    (pred_b - pred_a) * 100 if pred_a is not None and pred_b is not None
                    else None
                ),
                "original_frozen_bull_probability": old_frozen,
                "left_vs_frozen_pp": (
                    (pred_a - old_frozen) * 100 if pred_a is not None and old_frozen is not None
                    else None
                ),
                "right_vs_frozen_pp": (
                    (pred_b - old_frozen) * 100 if pred_b is not None and old_frozen is not None
                    else None
                ),
                "last_feature_hash_left": hash_a,
                "last_feature_hash_right": hash_b,
                "asof_feature_changed": hash_a != hash_b,
                "training_hash_left": pa["training_hash"],
                "training_hash_right": pb["training_hash"],
                "training_changed": pa["training_hash"] != pb["training_hash"],
                "trained_model_hash_left": pa["fitted_model_hash"],
                "trained_model_hash_right": pb["fitted_model_hash"],
                "trained_model_changed": pa["fitted_model_hash"] != pb["fitted_model_hash"],
                "train_rows_left": pa["training_rows"],
                "train_rows_right": pb["training_rows"],
                "classify_source": (
                    "INPUTS_IDENTICAL_MODEL_NUMERIC_NONDETERMINISM" if
                    hash_a == hash_b and pa["training_hash"] == pb["training_hash"] and
                    pred_a is not None and pred_b is not None and abs(pred_b - pred_a) > 1e-10 else
                    "HISTORICAL_TRAINING_INPUT_CHANGED" if
                    pa["training_hash"] != pb["training_hash"] else
                    "SIGNAL_FEATURE_CHANGED" if hash_a != hash_b else
                    "MODEL_UNAVAILABLE" if pred_a is None or pred_b is None else
                    "IDENTICAL_PREDICTION"
                ),
            })
    preds = pd.DataFrame(pred_rows).sort_values(["family", "symbol"])
    px = pd.DataFrame(price)
    technical = pd.DataFrame(features)
    changes = pd.DataFrame(revised, columns=["symbol","kind","date","changed_columns","changed_column_count"])
    out.mkdir(parents=True, exist_ok=True)
    px.to_csv(out / "price_column_diff.csv", index=False)
    technical.to_csv(out / "technical_column_diff.csv", index=False)
    changes.to_csv(out / "revised_sessions.csv", index=False)
    preds.to_csv(out / "model_replay.csv", index=False)
    # New policy is not trained or changed by these findings.
    provenance = {
        "version": VERSION, "status": "RESEARCH_HOLD_UNTIL_EXPLAINED",
        "research_only": True, "production_writes": False, "live_execution": False,
        "strategy_promoted": False, "asof_session": asof,
        "left_run_id": str(left_id), "right_run_id": str(right_id),
        "files_raw_parquet_sha_changed": count_changed_raw,
        "files_technical_parquet_sha_changed": count_changed_features,
        "symbols_with_semantic_raw_numeric_changes": count_changed_numeric,
        "raw_numeric_unchanged_symbols": [
            sym for sym in names if per_symbol[sym]["raw_numeric_same"]
        ],
        "close_series_globally_rescaled_symbols": [
            row["symbol"] for row in price
            if row["column"] == "close" and row["global_multiplicative_rescale"]
        ],
        "provider_configuration": {
            "provider": "yfinance",
            "auto_adjust_equities": True, "auto_adjust_vix": False,
            "repair": True, "keepna": True,
        },
        "identical_input_refit_deterministic": True,
        "changed_rows": len(changes),
        "trained_folds": len(preds),
        "train_input_changed": int(preds["training_changed"].sum()),
        "asof_feature_changed": int(preds["asof_feature_changed"].sum()),
        "model_parameters_changed": int(preds["trained_model_changed"].sum()),
        "probability_changed_gt_1pp": int((preds["prediction_delta_pp"].abs() > 1).sum()),
        "classification": preds["classify_source"].value_counts().to_dict(),
        "per_symbol": per_symbol,
        "environment": {
            "python": platform.python_version(), "platform": platform.platform(),
            "pandas": pd.__version__, "numpy": np.__version__,
            "sklearn": sklearn.__version__,
            "pyarrow": __import__("pyarrow").__version__,
        },
        "comparison_policy": {
            "float_atol": ABS_TOL, "float_rtol": REL_TOL,
            "fixed_asof": asof, "predefined_symbols": len(names),
            "incumbent_model": "annual expanding same frozen train/model functions",
            "independent_source_lineage_verified": False,
            "retrospective_2024_26_prospective": False,
        },
        "files": ("price_column_diff.csv", "technical_column_diff.csv",
                  "revised_sessions.csv", "model_replay.csv"),
    }
    write_json(out / "lineage_summary.json", provenance)
    print(json.dumps({"DAILY20_LINEAGE_AUDIT": {
        "left": left_id, "right": right_id, "price_revised_symbols": count_changed_numeric,
        "training_changed": provenance["train_input_changed"],
        "asof_changed": provenance["asof_feature_changed"],
        "prediction_delta_gt_1pp": provenance["probability_changed_gt_1pp"],
        "classification": provenance["classification"],
    }}))
    return provenance


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--left", required=True)
    p.add_argument("--right", required=True)
    p.add_argument("--left-run", required=True)
    p.add_argument("--right-run", required=True)
    p.add_argument("--asof", default="2026-11-20")
    p.add_argument("--config", default="research/kalman_daily20/universe.json")
    p.add_argument("--frozen-research", default="")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    run(a.left, a.right, load_spec(a.config), a.out,
        a.left_run, a.right_run, a.asof, a.frozen_research or None)


if __name__ == "__main__":
    main()
