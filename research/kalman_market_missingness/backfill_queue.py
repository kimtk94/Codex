#!/usr/bin/env python3
"""Inventory-first research market/macro backfill proposal, no price writes.

Two separately pinned Google Drive ZIP archives are read-only inputs. The
26-asset Daily20 archive may offer 9 same-Yahoo-provider *candidates* to fill
a 19-market-asset, 12-series FRED research archive, but no adjustments, data
vintages, missing prices, macro observations or signal journals are forged.
Only counts/dates/checksums/status are emitted (no redistributable OHLCV).
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd

from audit_missingness import date_keys, mode_market

VERSION = "kalman-backfill-proposal-cross-archive-v1"
MACRO_ID = "1aUhvIAsE2x2-LuKv5nSxmDGX0Uo4mqYd"
DAILY_ID = "1nWbyCiRSscJSqgZYvYhJ9DKHRlBwlKgE"
MACRO_MARKET_COUNT = 19
DAILY_MARKET_COUNT = 26
EXPECTED_FRED = (
    "CPIAUCSL", "DEXKOUS", "DFF", "DFII10", "DGS2", "DTWEXBGS",
    "M2SL", "NASDAQCOM", "SP500", "UNRATE", "VIXCLS", "WALCL",
)
PAIRED_SHARED = {
    "yf_gld", "yf_hyg", "yf_iwm", "yf_lqd", "yf_qqq",
    "yf_smh", "yf_spy", "yf_tlt", "yf_vix",
}
PRICE_KEYS = ("open", "high", "low", "close")
METADATA_ONLY = True


def require(ok, code):
    if not ok:
        raise ValueError("BACKFILL_" + code)


def sha(data):
    return sha256(data).hexdigest()


def validated_archives(macro_blob, daily_blob):
    require(isinstance(macro_blob, bytes) and
            isinstance(daily_blob, bytes) and
            0 < len(macro_blob) <= 35_000_000 and
            0 < len(daily_blob) <= 50_000_000, "ARCHIVE_SIZE_INVALID")
    mzip, dzip = ZipFile(BytesIO(macro_blob)), ZipFile(BytesIO(daily_blob))
    for archive in (mzip, dzip):
        names = archive.namelist()
        require(len(names) == len(set(names)) and
                not any(name.startswith("/") or "\\" in name or
                        ".." in Path(name).parts for name in names),
                "UNSAFE_ARCHIVE_MEMBER")
        require(archive.testzip() is None, "ARCHIVE_CRC_FAILED")
    macro = json.loads(mzip.read("manifest.json"))
    mready = json.loads(mzip.read("readiness.json"))
    daily = json.loads(dzip.read("drive_manifest.json"))
    require(macro.get("schema") == "kalman-daily-market-research-bundle-v1"
            and macro.get("research_only") is not False
            and macro.get("production_writes") is False
            and macro.get("market_assets") == MACRO_MARKET_COUNT
            and macro.get("feature_assets") == MACRO_MARKET_COUNT
            and macro.get("fred_series_success") == len(EXPECTED_FRED)
            and macro.get("fred_latest_revised_not_vintage_safe") is True,
            "MACRO_SOURCE_NOT_RESEARCH_HOLD")
    require(daily.get("format") == "kalman-daily20-drive-v1"
            and daily.get("research_only") is True
            and daily.get("production_writes") is False
            and daily.get("raw_symbols") == DAILY_MARKET_COUNT
            and daily.get("feature_symbols") == DAILY_MARKET_COUNT,
            "DAILY20_SOURCE_NOT_RESEARCH_HOLD")
    mm = macro.get("members")
    dm = daily.get("payload_hashes_sha256")
    require(isinstance(mm, list) and isinstance(dm, dict),
            "MANIFEST_MISSING_HASHES")
    macro_paths = [r["path"] for r in mm]
    require(len(macro_paths) == len(set(macro_paths))
            and set(macro_paths) == set(mzip.namelist()) -
            {"manifest.json", "readiness.json"}, "MACRO_MEMBER_SET_CHANGED")
    require(set(dm) == set(dzip.namelist()) - {"drive_manifest.json"},
            "DAILY20_MEMBER_SET_CHANGED")
    require(all(sha(mzip.read(r["path"])) == r["sha256"] for r in mm),
            "MACRO_SHA256_MISMATCH")
    require(all(sha(dzip.read(path)) == digest for path, digest in dm.items()),
            "DAILY20_SHA256_MISMATCH")
    market_paths = lambda z: {
        Path(n).stem: n for n in z.namelist()
        if n.startswith("market/raw/yfinance/") and n.endswith(".parquet")
    }
    a, b = market_paths(mzip), market_paths(dzip)
    require(len(a) == MACRO_MARKET_COUNT and len(b) == DAILY_MARKET_COUNT
            and len(set(a) & set(b)) == len(PAIRED_SHARED)
            and set(a) & set(b) == PAIRED_SHARED,
            "MARKET_UNIVERSE_CHANGED")
    require(set(EXPECTED_FRED) == set(
        json.loads(mzip.read("fred/fred_status.json")).get("series", {})
    ), "FRED_UNIVERSE_CHANGED")
    source_day = mready.get("expected_last_completed_nyse_session")
    target_day = daily.get("data_expected_last_closed_xnys")
    require(isinstance(source_day, str) and isinstance(target_day, str)
            and date.fromisoformat(source_day) <= date.fromisoformat(target_day),
            "ARCHIVE_SESSIONS_INVALID")
    require(mready.get("point_in_time_training_ready") is False
            and mready.get("production_writes") is False,
            "MACRO_POINT_IN_TIME_MISREPRESENTED")
    return mzip, dzip, macro, mready, daily, a, b


def frame_dates(frame, key):
    require("timestamp" in frame.columns, "MARKET_TIMESTAMP_MISSING:" + key)
    stamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    require(stamps.notna().all() and stamps.is_monotonic_increasing
            and not stamps.duplicated().any(), "MARKET_BAD_DATES:" + key)
    require(set(PRICE_KEYS).issubset(frame.columns),
            "MARKET_MISSING_OHLC:" + key)
    require("is_adjusted" in frame.columns,
            "MARKET_PRICE_BASIS_UNDECLARED:" + key)
    require(frame["is_adjusted"].nunique() == 1,
            "MIXED_ADJUSTMENT_BASIS:" + key)
    dates = stamps.dt.strftime("%Y-%m-%d")
    require(not dates.duplicated().any(),
            "DUPLICATE_SESSIONS:" + key)
    return dates


def shared_candidate(old_frame, new_frame, *, key, source_day, target_day):
    old_dates = frame_dates(old_frame, key)
    new_dates = frame_dates(new_frame, key)
    require(old_dates.max() >= source_day and new_dates.max() >= target_day,
            "INCOMPLETE_PRICE_SOURCE:" + key)
    original = old_frame.copy()
    candidate = new_frame.copy()
    original.index = old_dates.to_list()
    candidate.index = new_dates.to_list()
    shared = sorted(set(original.index) & set(candidate.index))
    require(len(shared) >= 12, "INSUFFICIENT_SHARED_PRICE_OVERLAP:" + key)
    # Use only the most recent overlap: prior observations may have undergone
    # valid later splits or distributions. Differences stay an uncertified HOLD.
    common = shared[-min(46, len(shared)):]
    repriced = 0
    max_delta_bp = 0.0
    incomplete = 0
    for col in PRICE_KEYS:
        earlier = pd.to_numeric(original.loc[common, col], errors="coerce")
        current = pd.to_numeric(candidate.loc[common, col], errors="coerce")
        both = earlier.notna() & current.notna() & earlier.gt(0) & current.gt(0)
        incomplete += int((~both).sum())
        if both.any():
            dev = (current[both] / earlier[both] - 1).abs()
            repriced += int((dev > 1e-9).sum())
            max_delta_bp = max(max_delta_bp, float(dev.max() * 10000))
    dates = sorted(x for x in candidate.index
                   if source_day < x <= target_day)
    mode = mode_market(key)
    expected = date_keys(str((date.fromisoformat(source_day)).fromordinal(
        date.fromisoformat(source_day).toordinal() + 1
    )), target_day, mode)
    available = set(dates) & expected
    require(len(available) == len(expected) or mode in (
        "US_DXY_XNYS_PROXY", "business"),
        "CANDIDATE_MISSING_REQUIRED_TAIL:" + key)
    basis_matches = (bool(original["is_adjusted"].iloc[0]) ==
                     bool(candidate["is_adjusted"].iloc[0]))
    return {
        "indicator": key, "layer": "MARKET", "frequency": mode,
        "source_last": source_day, "target_last": target_day,
        "expected_tail_rows": len(expected),
        "candidate_tail_rows": len(available),
        "candidate_missing_expected_rows": len(expected - available),
        "overlap_sessions_checked": len(common),
        "overlap_ohlc_repriced_fields": repriced,
        "overlap_ohlc_invalid_comparisons": incomplete,
        "overlap_max_absolute_revision_bp": round(max_delta_bp, 6),
        "adjustment_flag_matches": basis_matches,
        "reuse_status": "UNAPPROVED_SAME_PROVIDER_CANDIDATE_ONLY"
                        if basis_matches else "PRICE_ADJUSTMENT_BASIS_MISMATCH_HOLD",
        "backfill_action": "STAGE_FROZEN_CANDIDATE_WITH_REPRICING_AUDIT",
        "point_in_time_source_verified": False,
        "independent_official_close_verified": False,
        "can_modify_historical_archive": False,
    }


def make_plan(macro_blob, daily_blob, *, now=None):
    import exchange_calendars as xc
    mzip, dzip, mm, mr, dm, markets, daily = validated_archives(
        macro_blob, daily_blob)
    source_day = mr["expected_last_completed_nyse_session"]
    target_day = dm["data_expected_last_closed_xnys"]
    with mzip, dzip:
        queue = []
        for key in sorted(markets):
            mode = mode_market(key)
            old_frame = pd.read_parquet(BytesIO(mzip.read(markets[key])))
            actual_dates = frame_dates(old_frame, key)
            # Multi-market archives use one XNYS as-of in the manifest, while
            # BTC trades 24/7, USD/KRW can have Saturday-stamped bars, and
            # Korean markets have a separate exchange calendar. Subtracting
            # the uniform US date from BTC counts Oct 31 twice when it was
            # already present in the original immutable ZIP.
            asset_last = str(actual_dates.max())
            require(asset_last <= target_day,
                    "SOURCE_ASSET_OBSERVATION_AFTER_REFERENCE:" + key)
            expected = date_keys(str(date.fromordinal(
                date.fromisoformat(asset_last).toordinal() + 1
            )), target_day, mode)
            if key in daily:
                new_frame = pd.read_parquet(BytesIO(dzip.read(daily[key])))
                info = shared_candidate(old_frame, new_frame, key=key,
                                        source_day=asset_last,
                                        target_day=target_day)
            else:
                info = {
                    "indicator": key, "layer": "MARKET", "frequency": mode,
                    "source_last": asset_last, "target_last": target_day,
                    "expected_tail_rows": len(expected),
                    "candidate_tail_rows": 0,
                    "candidate_missing_expected_rows": len(expected),
                    "overlap_sessions_checked": 0,
                    "overlap_ohlc_repriced_fields": None,
                    "overlap_ohlc_invalid_comparisons": None,
                    "overlap_max_absolute_revision_bp": None,
                    "adjustment_flag_matches": None,
                    "reuse_status": "NOT_AVAILABLE_IN_DAILY20",
                    "backfill_action": "INDEPENDENT_SOURCE_REFETCH_AND_QC_REQUIRED",
                    "point_in_time_source_verified": False,
                    "independent_official_close_verified": False,
                    "can_modify_historical_archive": False,
                }
            queue.append(info)
        fred = json.loads(mzip.read("fred/fred_status.json"))
        fred_tasks = [{
            "series_id": sym, "last_observed": info.get("last_observation"),
            "date_asof_research_target": target_day,
            "source_record_revision": "LATEST_REVISED_NOT_ALFRED_PIT",
            "backfill_action": "REFETCH_PUBLICATION_FREQUENCY_AWARE",
            "fill_null_with_forward_data": False,
            "point_in_time_training_eligible": False,
            "archive_can_be_replaced": False,
        } for sym, info in sorted(fred["series"].items())]
        features = sorted(n for n in mzip.namelist()
                          if n.startswith("features/talib/") and n.endswith(".parquet"))
        require(len(features) == MACRO_MARKET_COUNT,
                "DERIVED_FEATURE_UNIVERSE_CHANGED")
    cross = sum(x["candidate_tail_rows"] for x in queue
                if x["indicator"] in PAIRED_SHARED)
    missing = sum(x["candidate_missing_expected_rows"] for x in queue)
    can_reuse = len([x for x in queue if x["candidate_tail_rows"] > 0])
    # Every required outstanding date must be accounted for exactly once
    # by a distinct staged candidate or an explicit refetch task; do not
    # count already observed off-market-day BTC/FX rows as missing.
    required_tail = sum(x["expected_tail_rows"] for x in queue)
    require(required_tail == cross + missing,
            "TAIL_LEDGER_CANDIDATE_ACCOUNTING_MISMATCH")
    shared_rows = [x for x in queue if x["indicator"] in PAIRED_SHARED]
    incompatible = [x for x in shared_rows
                    if x["adjustment_flag_matches"] is False]
    compatible = [x for x in shared_rows
                  if x["adjustment_flag_matches"] is True]
    require(len(shared_rows) == len(PAIRED_SHARED) and
            len(incompatible) + len(compatible) == len(shared_rows),
            "SHARED_ADJUSTMENT_BASIS_CLASSIFICATION_INCOMPLETE")
    require(all(x["reuse_status"] == "PRICE_ADJUSTMENT_BASIS_MISMATCH_HOLD"
                for x in incompatible) and
            all(x["reuse_status"] == "UNAPPROVED_SAME_PROVIDER_CANDIDATE_ONLY"
                for x in compatible),
            "UNSAFE_SHARED_SOURCE_STATUS")
    # Count candidate availability separately from approval. Matching Yahoo
    # provenance, even with matching is_adjusted, is not independent 16:00
    # exchange evidence; latest-revised FRED is not a historical PIT vintage.
    release_decision = {
        "decision": "HOLD",
        "reason_codes": [
            "SAME_PROVIDER_IS_NOT_INDEPENDENT_REGULAR_CLOSE",
            "PRICE_ADJUSTMENT_BASIS_MISMATCH" if incompatible else
            "PRICE_ADJUSTMENT_BASIS_NOT_INDEPENDENTLY_CERTIFIED",
            "INDEPENDENT_MARKET_REFETCH_REQUIRED",
            "FRED_LATEST_REVISED_NOT_POINT_IN_TIME",
            "DERIVED_FEATURES_REQUIRE_SOURCE_VINTAGE_REBUILD",
        ],
        "same_provider_available_asset_count": len(shared_rows),
        "same_provider_available_candidate_rows": cross,
        "incompatible_price_basis_asset_count": len(incompatible),
        "matching_adjustment_flag_but_uncertified_asset_count": len(compatible),
        "market_only_assets_to_refetch": MACRO_MARKET_COUNT - len(shared_rows),
        "unfilled_market_tail_rows": missing,
        "fred_series_blocked_for_pit_training": len(fred_tasks),
        "rebuild_technical_feature_assets_after_source_qc": len(features),
        "approved_market_assets_for_merge": 0,
        "approved_candidate_rows_for_merge": 0,
        "independently_certified_regular_closes": 0,
        "ready_for_pit_training": False,
        "ready_to_replace_original_drive_zip": False,
        "new_versioned_candidate_archive_created": False,
        "daily20_first_seal_touched": False,
        "requires_separate_source_qc_and_manual_promotion": True,
    }
    return {
        "version": VERSION,
        "release_decision": release_decision,
        "status": "BACKFILL_CANDIDATES_STAGED_METADATA_ONLY_RESEARCH_HOLD",
        "source_archive_drive_id": MACRO_ID,
        "source_archive_sha256": sha(macro_blob),
        "reference_archive_drive_id": DAILY_ID,
        "reference_archive_sha256": sha(daily_blob),
        "archive_integrity_sha256_pass": True,
        "source_last_completed_xnys": source_day,
        "reference_last_completed_xnys": target_day,
        "research_only": True, "production_writes": False,
        "live_execution": False, "strategy_promoted": False,
        "new_prospective_signals_created": 0,
        "market_assets": MACRO_MARKET_COUNT,
        "overlapping_same_vendor_assets": len(PAIRED_SHARED),
        "market_only_assets_need_new_collection": MACRO_MARKET_COUNT-len(PAIRED_SHARED),
        "same_vendor_candidate_tail_rows": cross,
        "candidate_missing_expected_tail_rows": missing,
        "market_expected_tail_rows_total": required_tail,
        "market_assets_with_any_reusable_candidate": can_reuse,
        "fred_series_require_republication_check": len(fred_tasks),
        "fred_latest_revised_not_pit": True,
        "feature_assets_need_recalculation_after_approved_source": len(features),
        "source_bars_modified": False,
        "original_drive_zip_overwritten": False,
        "automatically_merged": False,
        "daily20_first_seal_touched": False,
        "allowed_next": "RESEARCH_ONLY_BACKFILL_WITH_VERSIONED_NEW_ARCHIVE_AFTER_SOURCE_QC",
        "market_queue": queue,
        "fred_queue": fred_tasks,
    }


def csv_out(path, records):
    if not records:
        raise ValueError("BACKFILL_EMPTY_QUEUE")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(records[0]))
        wr.writeheader()
        wr.writerows(records)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--market-zip", required=True)
    p.add_argument("--daily20-zip", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    plan = make_plan(Path(args.market_zip).read_bytes(),
                     Path(args.daily20_zip).read_bytes())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "backfill_plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (out / "backfill_decision.json").write_text(
        json.dumps(plan["release_decision"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    csv_out(out / "backfill_market_queue.csv", plan["market_queue"])
    csv_out(out / "backfill_fred_queue.csv", plan["fred_queue"])
    print("KALMAN_CROSS_ARCHIVE_BACKFILL_HOLD",
          plan["source_last_completed_xnys"],
          plan["reference_last_completed_xnys"],
          "matching_asset_candidates", plan["overlapping_same_vendor_assets"],
          "other_provider_refetch", plan["market_only_assets_need_new_collection"],
          "fred_vintage_hold", plan["fred_series_require_republication_check"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
