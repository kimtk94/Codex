#!/usr/bin/env python3
"""Read-only comparison of original and freshly fetched wide-market research ZIPs.

Output only dates, counts, basis classifications and aggregate revision magnitudes.
Never merge prices, mutate a Drive object, or grant PIT/source certification.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

from refresh_ci import NEEDED, OPTIONAL, json_write

KEYS = NEEDED + OPTIONAL
OHLC = ("open", "high", "low", "close")
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def open_verified(blob):
    if not 0 < len(blob) <= MAX_ARCHIVE_BYTES:
        raise ValueError("ARCHIVE_SIZE_INVALID")
    z = zipfile.ZipFile(io.BytesIO(blob))
    names = z.namelist()
    if (len(names) != len(set(names)) or
            any(n.startswith("/") or "\\" in n or ".." in Path(n).parts for n in names) or
            sum(m.file_size for m in z.infolist()) > MAX_UNCOMPRESSED_BYTES):
        raise ValueError("UNSAFE_ARCHIVE_MEMBERS")
    if z.testzip() is not None:
        raise ValueError("ARCHIVE_CRC_FAILED")
    manifest = json.loads(z.read("manifest.json"))
    ready = json.loads(z.read("readiness.json"))
    if (manifest.get("schema") != "kalman-daily-market-research-bundle-v1" or
            manifest.get("status") != "RESEARCH_ONLY_VALIDATED" or
            manifest.get("production_writes") is not False or
            manifest.get("fred_latest_revised_not_vintage_safe") is not True or
            ready.get("production_writes") is not False or
            ready.get("point_in_time_training_ready") is not False):
        raise ValueError("UNSAFE_RESEARCH_MANIFEST")
    members = manifest["members"]
    paths = [m["path"] for m in members]
    if len(paths) != len(set(paths)) or set(paths) != set(names) - {"manifest.json", "readiness.json"}:
        raise ValueError("ARCHIVE_MEMBER_SET_MISMATCH")
    for member in members:
        data = z.read(member["path"])
        if len(data) != member["bytes"] or sha(data) != member["sha256"]:
            raise ValueError("ARCHIVE_MEMBER_HASH_MISMATCH")
    required = {f"market/raw/yfinance/{key}.parquet" for key in KEYS}
    if ({n for n in paths if n.startswith("market/")} != required or
            manifest.get("market_assets") != len(KEYS) or
            manifest.get("feature_assets") != len(KEYS) or
            sum(n.startswith("features/talib/") and n.endswith(".parquet") for n in paths) != len(KEYS)):
        raise ValueError("ARCHIVE_UNIVERSE_MISMATCH")
    return z, manifest, ready


def normalize(frame):
    required = {"timestamp", "is_adjusted", "symbol", "source", *OHLC}
    if not required.issubset(frame.columns) or frame.empty:
        raise ValueError("MARKET_SCHEMA_INVALID")
    dates = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    if dates.isna().any() or not dates.is_monotonic_increasing:
        raise ValueError("MARKET_TIMESTAMP_INVALID")
    dates = dates.dt.strftime("%Y-%m-%d")
    if dates.duplicated().any():
        raise ValueError("MARKET_DUPLICATE_DATES")
    basis = frame["is_adjusted"]
    if basis.isna().any() or not all(isinstance(v, (bool, np.bool_)) for v in basis) or basis.nunique() != 1:
        raise ValueError("MARKET_PRICE_BASIS_UNKNOWN")
    identities = []
    for col in ("symbol", "source"):
        values = frame[col]
        if values.isna().any() or values.nunique() != 1 or not str(values.iloc[0]).strip():
            raise ValueError("MARKET_IDENTITY_UNKNOWN")
        identities.append(str(values.iloc[0]))
    values = frame.loc[:, OHLC].apply(pd.to_numeric, errors="coerce")
    values.index = dates
    valid = pd.DataFrame(np.isfinite(values.to_numpy()), index=values.index, columns=values.columns) & values.gt(0)
    bad = ~valid.all(axis=1)
    inconsistent = (values["high"] < values[["open", "low", "close"]].max(axis=1)
                    ) | (values["low"] > values[["open", "high", "close"]].min(axis=1))
    return values, valid, bool(basis.iloc[0]), tuple(identities), int(bad.sum()), int((~bad & inconsistent).sum())


def compare_frames(old_frame, new_frame, key):
    old, old_valid, old_basis, old_identity, old_invalid, old_ohlc = normalize(old_frame)
    new, new_valid, new_basis, new_identity, new_invalid, new_ohlc = normalize(new_frame)
    shared = sorted(set(old.index) & set(new.index))
    old_last, new_last = str(old.index.max()), str(new.index.max())
    original_only = set(old.index) - set(new.index)
    historical_omissions = sum(d < str(new.index.min()) for d in original_only)
    internal_omissions = len(original_only) - historical_omissions
    tail = sorted(d for d in new.index if d > old_last)
    matching_basis = old_basis == new_basis
    matching_identity = old_identity == new_identity
    # The numerical differences are diagnostics only, not comparable returns
    # or official close certification (even when provider and basis match).
    valid = old_valid.loc[shared] & new_valid.loc[shared]
    ratios = (new.loc[shared].where(valid) / old.loc[shared].where(valid) - 1).abs()
    finite = ratios.to_numpy()[np.isfinite(ratios.to_numpy())]
    reasons = ["INDEPENDENT_CLOSE_AND_FACTOR_CERTIFICATION_REQUIRED"]
    if not matching_basis:
        reasons.append("ADJUSTMENT_BASIS_MISMATCH")
    if not matching_identity:
        reasons.append("SOURCE_OR_SYMBOL_MISMATCH")
    if len(shared) < 20:
        reasons.append("INSUFFICIENT_OVERLAP")
    if original_only:
        reasons.append("ORIGINAL_HISTORY_NOT_FULLY_PRESENT")
    if new_last < old_last:
        reasons.append("CANDIDATE_BEHIND_ORIGINAL")
    if new_invalid or new_ohlc:
        reasons.append("CANDIDATE_OHLC_QC_REQUIRED")
    return {
        "key": key,
        "original_first": str(old.index.min()), "original_last": old_last,
        "candidate_first": str(new.index.min()), "candidate_last": new_last,
        "original_rows": len(old), "candidate_rows": len(new),
        "overlap_rows": len(shared), "new_tail_rows": len(tail),
        "original_dates_omitted_before_candidate_start": historical_omissions,
        "original_dates_omitted_within_or_after_candidate_range": internal_omissions,
        "adjustment_basis_matches": matching_basis,
        "original_adjusted": old_basis, "candidate_adjusted": new_basis,
        "source_and_symbol_match": matching_identity,
        "overlap_valid_ohlc_fields": int(valid.to_numpy().sum()),
        "overlap_invalid_ohlc_fields": int(valid.size - valid.to_numpy().sum()),
        "overlap_repriced_fields": int((finite > 1e-9).sum()),
        "overlap_max_absolute_revision_bp": round(float(finite.max() * 10000), 6) if finite.size else None,
        "original_invalid_price_rows": old_invalid, "candidate_invalid_price_rows": new_invalid,
        "original_inconsistent_ohlc_rows": old_ohlc, "candidate_inconsistent_ohlc_rows": new_ohlc,
        "reason_codes": reasons, "release": "HOLD",
    }


def compare_archives(original, candidate):
    original = Path(original).read_bytes()
    candidate = Path(candidate).read_bytes()
    old, old_manifest, old_ready = open_verified(original)
    new, new_manifest, new_ready = open_verified(candidate)
    with old, new:
        rows = []
        for key in KEYS:
            path = f"market/raw/yfinance/{key}.parquet"
            rows.append(compare_frames(pd.read_parquet(io.BytesIO(old.read(path))),
                                       pd.read_parquet(io.BytesIO(new.read(path))), key))
    return {
        "schema": "kalman-market-overlap-audit-v1",
        "status": "CANDIDATE_COMPARISON_RESEARCH_HOLD",
        "original_sha256": sha(original), "candidate_sha256": sha(candidate),
        "original_asof": old_ready.get("expected_last_completed_nyse_session"),
        "candidate_asof": new_ready.get("expected_last_completed_nyse_session"),
        "assets_compared": len(rows),
        "assets_matching_basis": sum(r["adjustment_basis_matches"] for r in rows),
        "assets_matching_source_identity": sum(r["source_and_symbol_match"] for r in rows),
        "assets_with_original_dates_omitted": sum(bool(r["original_dates_omitted_before_candidate_start"] +
                                                       r["original_dates_omitted_within_or_after_candidate_range"]) for r in rows),
        "candidate_tail_rows_observed": sum(r["new_tail_rows"] for r in rows),
        "candidate_invalid_price_rows": sum(r["candidate_invalid_price_rows"] for r in rows),
        "candidate_inconsistent_ohlc_rows": sum(r["candidate_inconsistent_ohlc_rows"] for r in rows),
        "original_fred_ready_series": old_manifest.get("fred_series_success"),
        "candidate_fred_ready_series": new_manifest.get("fred_series_success"),
        "assets": rows,
        "independent_regular_close_certified_assets": 0,
        "approved_assets_for_merge": 0, "approved_rows_for_merge": 0,
        "original_drive_zip_replaced": False, "private_candidate_archive_persisted": False,
        "ready_for_pit_training": False, "production_writes": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--original", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    report = compare_archives(args.original, args.candidate)
    json_write(args.out, report)
    print(json.dumps({k: v for k, v in report.items() if k != "assets"}))


if __name__ == "__main__":
    main()
