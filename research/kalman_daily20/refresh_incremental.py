#!/usr/bin/env python3
"""Daily20 incremental Yahoo fetch from pinned, checksum-verified Google Drive data.

Research-only. Weekly full reconciliation guards against historical adjusted
price revisions. Never writes to the Drive source; publisher remains separate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import sys
from zipfile import ZipFile

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GATEWAY = ROOT / "kalman-toss-gateway"
sys.path.insert(0, str(GATEWAY))

from daily20 import market_file, load_bars, write_json  # noqa: E402

CACHE_ID = "1nWbyCiRSscJSqgZYvYhJ9DKHRlBwlKgE"
CACHE_NAME = "daily20_data_latest.zip"
RESULTS_ID = "1l-e4OLKS4qlDjNsf8TdkMsd5w3QouF4w"
RESULTS_NAME = "daily20_results_latest.zip"
LOOKBACK_CALENDAR_DAYS = 46
FULL_REFRESH_UTC_WEEKDAY = 5  # Saturday: reconcile previous Friday session
MAX_CACHE_STALENESS_DAYS = 14
MAX_OVERLAP_MEDIAN_DRIFT = 0.0025   # 0.25% median adjusted OHLC revision
MAX_OVERLAP_P95_DRIFT = 0.0100     # 1% material outlier
MIN_OVERLAP_SESSIONS = 12


def sha256_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


def read_verified_cache(archive, expected_keys):
    """Verify ZIP manifest, 26 raw data files and every published per-file SHA256."""
    with ZipFile(BytesIO(archive)) as zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("CACHE_DUPLICATED_MEMBERS")
        if any(name.startswith("/") or ".." in Path(name).parts or "\\" in name for name in names):
            raise RuntimeError("UNSAFE_ZIP_PATH")
        if "drive_manifest.json" not in names:
            raise RuntimeError("CACHE_MISSING_PERSISTENCE_MANIFEST")
        manifest = json.loads(zf.read("drive_manifest.json"))
        if manifest.get("format") != "kalman-daily20-drive-v1" or manifest.get("research_only") is not True:
            raise RuntimeError("UNEXPECTED_DATA_CACHE_VERSION")
        if manifest.get("production_writes") is not False:
            raise RuntimeError("CACHE_PRODUCTION_WRITE_FLAG")
        hashes = manifest.get("payload_hashes_sha256", {})
        if set(hashes) != set(names) - {"drive_manifest.json"}:
            raise RuntimeError("CACHE_HASH_MANIFEST_INCOMPLETE")
        if any(sha256_bytes(zf.read(name)) != digest for name, digest in hashes.items()):
            raise RuntimeError("CACHE_HASH_MISMATCH")
        raw_names = {f"market/raw/yfinance/{key}.parquet" for key in expected_keys}
        observed = {n for n in names if n.startswith("market/raw/yfinance/") and n.endswith(".parquet")}
        if observed != raw_names:
            raise RuntimeError("CACHE_RAW_UNIVERSE_MISMATCH")
        if manifest.get("raw_symbols") != 26 or manifest.get("feature_symbols") != 26:
            raise RuntimeError("CACHE_SYMBOL_COUNT_MISMATCH")
        frames = {key: pd.read_parquet(BytesIO(zf.read(f"market/raw/yfinance/{key}.parquet")))
                  for key in expected_keys}
    return manifest, frames


def download_prior_archive(credentials, *, file_id=CACHE_ID, expected_name=CACHE_NAME):
    import googleapiclient.discovery
    from googleapiclient.http import MediaIoBaseDownload
    service = googleapiclient.discovery.build(
        "drive", "v3", credentials=credentials, cache_discovery=False
    )
    metadata = service.files().get(
        fileId=file_id, fields="id,name,mimeType,size,md5Checksum", supportsAllDrives=True
    ).execute()
    if metadata.get("name") != expected_name or metadata.get("mimeType") != "application/zip":
        raise RuntimeError("UNEXPECTED_CACHE_IDENTITY")
    if int(metadata.get("size", 0)) > 50_000_000:
        raise RuntimeError("CACHE_UNEXPECTED_SIZE")
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    stream = BytesIO()
    downloader = MediaIoBaseDownload(stream, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    data = stream.getvalue()
    if not data or hashlib.md5(data).hexdigest() != metadata.get("md5Checksum"):
        raise RuntimeError("CACHE_DRIVE_MD5_MISMATCH")
    return data


def validate_old_frame(frame, symbol):
    """Reject cached data with altered schema, duplicates, or wrong ticker."""
    required = {"timestamp", "market", "symbol", "open", "high", "low", "close", "volume", "is_adjusted"}
    if not required.issubset(frame.columns):
        raise RuntimeError(f"CACHE_SCHEMA_MISMATCH {symbol}")
    if not frame["symbol"].eq(symbol).all():
        raise RuntimeError(f"CACHE_WRONG_SYMBOL {symbol}")
    stamp = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if stamp.duplicated().any() or stamp.isna().any():
        raise RuntimeError(f"CACHE_DUPLICATE_TIMESTAMP {symbol}")
    if len(frame) < 252:
        raise RuntimeError(f"CACHE_TOO_SHORT {symbol}")
    if frame["is_adjusted"].nunique() != 1 or bool(frame["is_adjusted"].iloc[0]) != (symbol != "VIX"):
        raise RuntimeError(f"CACHE_ADJUSTMENT_MISMATCH {symbol}")
    return stamp.max().date()


def overlap_diagnostics(old, fresh):
    """Compare same-session adjusted OHLC; return material-revision evidence."""
    cols = ("open", "high", "low", "close")
    def normalize(df):
        x = df.copy()
        x.index = pd.to_datetime(x["timestamp"], utc=True).dt.normalize()
        return x[list(cols)].apply(pd.to_numeric, errors="coerce")
    a, b = normalize(old), normalize(fresh)
    overlap = a.join(b, how="inner", lsuffix="_old", rsuffix="_new")
    close_pairs = overlap[["close_old", "close_new"]].dropna()
    if len(close_pairs) < MIN_OVERLAP_SESSIONS:
        return {"overlap_sessions": len(close_pairs), "revision": True, "reason": "LOW_OVERLAP"}
    relative = []
    for col in cols:
        p = overlap[f"{col}_old"]
        q = overlap[f"{col}_new"]
        matched = p.notna() & q.notna() & p.gt(0)
        relative.extend((q[matched] / p[matched] - 1).abs().tolist())
    if not relative:
        return {"overlap_sessions": len(close_pairs), "revision": True, "reason": "NO_FINITE_OHLC"}
    import numpy as np
    median = float(np.median(relative))
    p95 = float(np.quantile(relative, 0.95))
    revision = median > MAX_OVERLAP_MEDIAN_DRIFT or p95 > MAX_OVERLAP_P95_DRIFT
    return {"overlap_sessions": len(close_pairs), "median_abs_reprice": median,
            "p95_abs_reprice": p95, "revision": bool(revision),
            "reason": "MATERIAL_ADJUSTED_PRICE_REVISION" if revision else "OK"}


def combine_history(old, recent):
    """New observations win within the overlap, historical rows are never projected."""
    a, b = old.copy(), recent.copy()
    a["_refresh"] = 0
    b["_refresh"] = 1
    merged = pd.concat([a, b], ignore_index=True)
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True).dt.tz_localize(None)
    merged = merged.sort_values(["timestamp", "_refresh"])
    merged = merged.drop_duplicates("timestamp", keep="last").drop(columns=["_refresh"])
    merged = merged.reset_index(drop=True)
    if len(merged) < len(old):
        raise RuntimeError("MERGE_HISTORY_SHRANK")
    if merged["timestamp"].isna().any() or merged["timestamp"].duplicated().any():
        raise RuntimeError("MERGE_INVALID_DATES")
    return merged


def full_refresh(universe, output, end, reason):
    from engine.market_data.cli import Settings, build
    status, ret = build(Settings(output_dir=Path(output), start_date="2017-01-01",
                                 end_date=end, universe_path=Path(universe)))
    if ret != 0 or status.get("required_failures"):
        raise RuntimeError("FULL_REFRESH_REQUIRED_DATA_FAILED")
    report = {"mode": "FULL_HISTORY", "reason": reason, "asset_count": 26,
              "end_exclusive": end, "status": status["status"]}
    write_json(Path(output) / "refresh_mode.json", report)
    print(json.dumps({"DAILY20_REFRESH": report}))
    return report


def incremental_refresh(universe_path, output, end, cache_bytes, *,
                        now=None, provider=None, write=None):
    from engine.market_data.base import ProviderRequest
    from engine.market_data.snapshot import write_snapshot, atomic_json
    universe = json.loads(Path(universe_path).read_text())
    assets = universe["assets"]
    if len(assets) != 26:
        raise RuntimeError("INVALID_UNIVERSE_COUNT")
    expected_keys = {item["key"] for item in assets}
    manifest, old_map = read_verified_cache(cache_bytes, expected_keys)
    if manifest.get("universe_version") != universe.get("version"):
        raise RuntimeError("CACHE_UNIVERSE_VERSION_CHANGED")
    verified_session = pd.Timestamp(manifest.get("data_expected_last_closed_xnys"))
    if pd.isna(verified_session):
        raise RuntimeError("CACHE_SESSION_INVALID")
    end_day = pd.Timestamp(end) - pd.Timedelta(days=1)
    if end_day < verified_session:
        raise RuntimeError("CACHED_DATA_NEWER_THAN_TARGET_END")
    if (end_day - verified_session).days > MAX_CACHE_STALENESS_DAYS:
        return full_refresh(universe_path, output, end, "CACHE_TOO_STALE")
    if provider is None:
        from engine.market_data.yfinance_provider import YFinanceProvider
        provider = YFinanceProvider()
    refreshed, details = {}, {}
    for asset in assets:
        key, symbol = asset["key"], asset["symbol"]
        old = old_map[key]
        validate_old_frame(old, symbol)
        last_old = pd.to_datetime(old["timestamp"], utc=True).max()
        request_start = (last_old - timedelta(days=LOOKBACK_CALENDAR_DAYS)).date().isoformat()
        req = ProviderRequest(
            symbol=symbol, provider_symbol=asset["provider_symbol"],
            start=request_start, end=end, interval="1d",
            market=asset["market"], currency=asset["currency"],
            kind=asset["kind"], adjusted=bool(asset["adjusted"]),
        )
        result = provider.fetch(req)
        if result.metadata.get("status") != "READY" or result.data.empty:
            raise RuntimeError("RECENT_PRICE_DOWNLOAD_FAILED: " + key)
        diag = overlap_diagnostics(old, result.data)
        details[key] = diag
        if diag["revision"]:
            # Never stitch a revised adjustment factor into an older price scale.
            return full_refresh(universe_path, output, end, f"OVERLAP_REPRICE_{key}_{diag['reason']}")
        combined = combine_history(old, result.data)
        refreshed[key] = (combined, result.metadata)
    sources = {}
    for asset in assets:
        key = asset["key"]
        frame, meta = refreshed[key]
        path = Path(output) / "raw" / "yfinance" / f"{key}.parquet"
        snapshot = write_snapshot(frame, path, metadata={
            **meta, "required": True, "group": asset["group"],
            "refresh_mode": "INCREMENTAL", "cached_session": str(verified_session.date()),
            "overlap": details[key], "universe_version": universe["version"]
        })
        sources[key] = {"status": "READY", "required": True, "manifest": snapshot}
    summary = {"status": "READY", "shadow_only": True, "production_writes": False,
               "asset_count": 26, "required_failures": [], "optional_issues": [],
               "comparison_failures": [], "sources": sources}
    atomic_json(Path(output) / "market_data_v2_run_status.json", summary)
    report = {"mode": "INCREMENTAL", "status": "READY",
              "cache_session": str(verified_session.date()), "end_exclusive": end,
              "asset_count": 26, "lookback_calendar_days": LOOKBACK_CALENDAR_DAYS,
              "overlap": details, "historical_price_scale_revised": False}
    write_json(Path(output) / "refresh_mode.json", report)
    print(json.dumps({"DAILY20_REFRESH": {"mode": report["mode"], "asset_count": 26}}))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--universe", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--no-drive", action="store_true", help="PR tests use independent full historical download")
    p.add_argument("--force-full", action="store_true")
    p.add_argument("--restore-only", action="store_true",
                   help="Download pinned Drive snapshot in credential-isolated Actions job")
    p.add_argument("--archive-output", default="",
                   help="Path to write downloaded archive in restore-only mode")
    p.add_argument("--results-archive-output", default="",
                   help="Also restore and verify prior OOS results ZIP for forward-only journal")
    p.add_argument("--cache-file", default="",
                   help="Read a prior downloaded Drive snapshot; no credentials needed")
    a = p.parse_args()
    now = datetime.now(timezone.utc)
    if a.restore_only:
        if not a.archive_output:
            raise ValueError("--archive-output is required for restore-only mode")
        from publish_drive import credentials_from_env
        credentials = credentials_from_env()
        archived = download_prior_archive(credentials)
        archive_path = Path(a.archive_output)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_bytes(archived)
        # Parse now to fail immediately if an archive is corrupted or points to a different universe.
        universe = json.loads(Path(a.universe).read_text())
        read_verified_cache(archived, {item["key"] for item in universe["assets"]})
        if a.results_archive_output:
            from forward_shadow import validate_prior_results_archive
            research_archive = download_prior_archive(
                credentials, file_id=RESULTS_ID, expected_name=RESULTS_NAME
            )
            core = {asset["provider_symbol"] for asset in universe["assets"]
                    if asset["group"] == "DAILY20_CORE"}
            validate_prior_results_archive(research_archive, core)
            path = Path(a.results_archive_output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(research_archive)
            print(json.dumps({"DAILY20_FORWARD_PRIOR_RESTORED": True,
                              "bytes": len(research_archive)}))
        print(json.dumps({"DAILY20_CACHE_RESTORED": True, "bytes": len(archived)}))
        return
    if a.no_drive or a.force_full or now.weekday() == FULL_REFRESH_UTC_WEEKDAY:
        return full_refresh(a.universe, a.output_dir, a.end_date,
                            "PR_FULL" if a.no_drive else "WEEKLY_OR_FORCE_FULL")
    if not a.cache_file:
        raise ValueError("Incremental refresh requires --cache-file from approved restore job")
    archived = Path(a.cache_file).read_bytes()
    return incremental_refresh(a.universe, a.output_dir, a.end_date, archived, now=now)


if __name__ == "__main__":
    main()
