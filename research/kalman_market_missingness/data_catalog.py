"""Metadata-only catalogue derived from the existing verified backfill plan.

No raw prices, archive mutation, PIT approval, or live execution. Reuse the
existing missingness workflow rather than creating another scheduled workflow.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
import json
from pathlib import Path
import re

from backfill_queue import (DAILY_ID, MACRO_ID, EXPECTED_FRED, PAIRED_SHARED,
                            MACRO_MARKET_COUNT, VERSION as PLAN_VERSION)

VERSION = "kalman-market-data-catalog-v1"
FALSE_FLAGS = (
    "production_writes", "live_execution", "strategy_promoted",
    "source_bars_modified", "original_drive_zip_overwritten",
    "automatically_merged", "daily20_first_seal_touched",
)
WIDE_ONLY = {
    "yf_btc", "yf_dia", "yf_dxy", "yf_ixic", "yf_kosdaq", "yf_kospi",
    "yf_soxx", "yf_sp500", "yf_tnx", "yf_usdkrw",
}
FIELDS = (
    "dataset", "layer", "source_archive", "source_sha256", "last_observed",
    "reference_session", "frequency", "candidate_rows", "missing_rows",
    "state", "next_action", "pit_approved", "canonical_write_allowed",
)


def require(condition, code):
    if not condition:
        raise ValueError("CATALOG_" + code)


def count(value):
    return type(value) is int and value >= 0


def iso(value):
    require(isinstance(value, str), "DATE_INVALID")
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def build_catalog(plan):
    require(isinstance(plan, dict), "PLAN_INVALID")
    require(plan.get("version") == PLAN_VERSION and
            plan.get("status") == "BACKFILL_CANDIDATES_STAGED_METADATA_ONLY_RESEARCH_HOLD",
            "PLAN_VERSION_OR_STATUS")
    require(plan.get("research_only") is True and
            plan.get("archive_integrity_sha256_pass") is True and
            plan.get("fred_latest_revised_not_pit") is True and
            all(plan.get(k) is False for k in FALSE_FLAGS) and
            type(plan.get("new_prospective_signals_created")) is int and
            plan["new_prospective_signals_created"] == 0,
            "UNSAFE_PLAN")
    require(plan.get("source_archive_drive_id") == MACRO_ID and
            plan.get("reference_archive_drive_id") == DAILY_ID, "ARCHIVE_ID")
    source_sha = plan.get("source_archive_sha256")
    reference_sha = plan.get("reference_archive_sha256")
    require(all(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v)
                for v in (source_sha, reference_sha)), "ARCHIVE_SHA")
    source_day = plan.get("source_last_completed_xnys")
    reference_day = plan.get("reference_last_completed_xnys")
    require(iso(source_day) and iso(reference_day) and source_day <= reference_day,
            "ARCHIVE_SESSION")
    market, fred = plan.get("market_queue"), plan.get("fred_queue")
    require(isinstance(market, list) and isinstance(fred, list) and
            all(isinstance(r, dict) for r in market + fred), "QUEUE_INVALID")
    require(len(market) == MACRO_MARKET_COUNT and
            {r.get("indicator") for r in market} == PAIRED_SHARED | WIDE_ONLY and
            len(fred) == len(EXPECTED_FRED) and
            {r.get("series_id") for r in fred} == set(EXPECTED_FRED),
            "QUEUE_UNIVERSE")
    require(plan.get("market_assets") == 19 and
            plan.get("overlapping_same_vendor_assets") == 9 and
            plan.get("market_only_assets_need_new_collection") == 10 and
            plan.get("fred_series_require_republication_check") == 12 and
            plan.get("feature_assets_need_recalculation_after_approved_source") == 19,
            "SUMMARY_UNIVERSE")
    rows = []
    totals = [0, 0, 0]
    def row(dataset, layer, last, frequency, candidates, missing, state, action):
        return dict(zip(FIELDS, (
            dataset, layer, MACRO_ID, source_sha, last, reference_day, frequency,
            candidates, missing, state, action, False, False,
        )))
    for item in sorted(market, key=lambda r: r["indicator"]):
        key = item["indicator"]
        last = item.get("source_last")
        frequency = item.get("frequency")
        require(iso(last) and last <= reference_day and
                item.get("target_last") == reference_day and
                isinstance(frequency, str) and bool(frequency.strip()), "MARKET_DATE")
        require(all(item.get(k) is False for k in (
            "point_in_time_source_verified", "independent_official_close_verified",
            "can_modify_historical_archive")), "MARKET_UNSAFE")
        expected, candidate, missing = (item.get(k) for k in (
            "expected_tail_rows", "candidate_tail_rows", "candidate_missing_expected_rows"))
        require(all(count(v) for v in (expected, candidate, missing)) and
                expected == candidate + missing, "MARKET_ROW_ACCOUNTING")
        if key in PAIRED_SHARED:
            basis = item.get("adjustment_flag_matches")
            require(type(basis) is bool, "MARKET_BASIS")
            status = ("UNAPPROVED_SAME_PROVIDER_CANDIDATE_ONLY" if basis else
                      "PRICE_ADJUSTMENT_BASIS_MISMATCH_HOLD")
            require(item.get("reuse_status") == status, "MARKET_STATE")
            action = "STAGE_FROZEN_CANDIDATE_WITH_REPRICING_AUDIT"
        else:
            require(candidate == 0 and item.get("adjustment_flag_matches") is None and
                    item.get("reuse_status") == "NOT_AVAILABLE_IN_DAILY20",
                    "MARKET_EXTERNAL_SOURCE")
            status = "EXTERNAL_SOURCE_REFETCH_HOLD"
            action = "INDEPENDENT_SOURCE_REFETCH_AND_QC_REQUIRED"
        totals = [a+b for a,b in zip(totals, (expected, candidate, missing))]
        rows.append(row(key, "MARKET", last, frequency, candidate, missing, status, action))
        rows.append(row(key, "FEATURE", None, frequency, None, None,
                        "REBUILD_AFTER_APPROVED_SOURCE_HOLD",
                        "REGENERATE_FEATURES_FROM_VERSIONED_QC_INPUT"))
    require(all(count(plan.get(k)) and plan[k] == v for k,v in zip((
        "market_expected_tail_rows_total", "same_vendor_candidate_tail_rows",
        "candidate_missing_expected_tail_rows"), totals)), "SUMMARY_ACCOUNTING")
    require(plan.get("market_assets_with_any_reusable_candidate") ==
            sum(r["candidate_tail_rows"] > 0 for r in market), "SUMMARY_CANDIDATE_ASSETS")
    for item in sorted(fred, key=lambda r: r["series_id"]):
        last = item.get("last_observed")
        require(last is None or iso(last), "FRED_DATE")
        require(item.get("date_asof_research_target") == reference_day and
                item.get("source_record_revision") == "LATEST_REVISED_NOT_ALFRED_PIT" and
                all(item.get(k) is False for k in ("fill_null_with_forward_data",
                    "point_in_time_training_eligible", "archive_can_be_replaced")),
                "FRED_UNSAFE")
        rows.append(row(item["series_id"], "FRED", last, "PUBLICATION_FREQUENCY_REQUIRED",
                        None, None, "LATEST_REVISED_NOT_PIT_HOLD",
                        "REFETCH_PUBLICATION_FREQUENCY_AWARE"))
    return {
        "version": VERSION, "research_only": True, "production_writes": False,
        "live_execution": False, "strategy_promoted": False,
        "approved_backfill_rows": 0, "pit_training_approved": False,
        "canonical_archive_replacement_allowed": False,
        "status": "CATALOG_METADATA_ONLY_RESEARCH_HOLD",
        "source_archive": {"drive_id": MACRO_ID, "sha256": source_sha,
                           "session": source_day},
        "reference_archive": {"drive_id": DAILY_ID, "sha256": reference_sha,
                              "session": reference_day, "raw_assets": 26, "feature_assets": 26},
        "market_rows": 19, "feature_rows": 19, "fred_rows": 12,
        "expected_tail_rows": totals[0], "candidate_tail_rows": totals[1],
        "missing_tail_rows": totals[2], "datasets": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    catalog = build_catalog(json.loads(Path(args.plan).read_text(encoding="utf-8")))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "data_catalog.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    with (out / "data_catalog.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(catalog["datasets"])
    print("KALMAN_DATA_CATALOG_HOLD", "datasets", len(catalog["datasets"]),
          "candidate_rows", catalog["candidate_tail_rows"],
          "missing_rows", catalog["missing_tail_rows"], "approved_rows", 0)


if __name__ == "__main__":
    main()
