#!/usr/bin/env python3
"""Publish Daily20 research-only GitHub artifact payloads to two pinned Drive files.

Only applies to verified complete OOS data. Must never contact broker, model
production tables, deploy web, or create extra Drive files.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

EXPECTED_TARGETS = {
    "data": ("1nWbyCiRSscJSqgZYvYhJ9DKHRlBwlKgE", "daily20_data_latest.zip"),
    "results": ("1l-e4OLKS4qlDjNsf8TdkMsd5w3QouF4w", "daily20_results_latest.zip"),
}
EXPECTED_SERVICE_ACCOUNT = "ckd-research-automation@novogene-css-automation.iam.gserviceaccount.com"


def md5_file(path):
    digest = hashlib.md5()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_payload(data_root, results_root):
    """Fail before authenticating if any required piece is absent or stale."""
    d, r = Path(data_root), Path(results_root)
    qc_path = r / "qc.json"
    summary_path = r / "research" / "summary.json"
    universe_path = r / "universe-derived.json"
    for p in (qc_path, summary_path, universe_path):
        if not p.is_file():
            raise RuntimeError("MISSING_EVIDENCE: " + p.name)
    qc = json.loads(qc_path.read_text())
    summary = json.loads(summary_path.read_text())
    universe = json.loads(universe_path.read_text())

    if qc.get("status") != "READY" or qc.get("required") != 26 or qc.get("ready") != 26:
        raise RuntimeError("DATA_QC_NOT_26_OF_26_READY")
    if summary.get("research_only") is not True or summary.get("live_execution") is not False:
        raise RuntimeError("RESEARCH_ISOLATION_BROKEN")
    if summary.get("latest_score_count") != 20:
        raise RuntimeError("NOT_ALL_20_OOS_SCORES")
    if len(universe.get("assets", [])) != 26:
        raise RuntimeError("NOT_A_26_ASSET_UNIVERSE")

    # A successful Daily20 run must include a complete cash-ledger portfolio
    # audit. Never publish only per-trade averages as a "validated" result.
    portfolio_path = r / "research" / "portfolio_summary.json"
    required_portfolio_files = [
        portfolio_path,
        r / "research" / "portfolio_daily_equity.csv",
        r / "research" / "portfolio_executions.csv",
        r / "research" / "portfolio_annual.csv",
        r / "research" / "portfolio_scenarios.csv",
    ]
    if not all(p.is_file() and p.stat().st_size > 10 for p in required_portfolio_files):
        raise RuntimeError("PORTFOLIO_EVIDENCE_INCOMPLETE")
    portfolio = json.loads(portfolio_path.read_text())
    if (portfolio.get("research_only") is not True
            or portfolio.get("live_execution") is not False
            or portfolio.get("portfolio_mdd_available") is not True
            or portfolio.get("tradable_strategy_approved") is not False
            or portfolio.get("scenario_count") != 16
            or len(portfolio.get("primary_scenarios", [])) != 4
            or set(portfolio.get("benchmark", {})) != {"SPY", "QQQ"}):
        raise RuntimeError("PORTFOLIO_GOVERNANCE_VALIDATION_FAILED")

    bear_dir = r / "research" / "regime_challenger"
    files = [
        "regime_summary.json", "regime_scenarios.csv",
        "regime_daily_equity.csv", "regime_executions.csv",
        "regime_annual.csv", "regime_year_coverage.csv",
        "regime_session_context.csv", "bear_model_coverage.csv",
        "bear_oos_trades.csv",
        "baseline_loss_attribution.csv", "baseline_loss_attribution.json",
    ]
    if not all((bear_dir / name).is_file() and (bear_dir / name).stat().st_size > 10
               for name in files):
        raise RuntimeError("BEAR_RESEARCH_EVIDENCE_INCOMPLETE")
    bear = json.loads((bear_dir / "regime_summary.json").read_text())
    if (bear.get("version") != "daily20-bear-oos-v1"
            or bear.get("research_only") is not True
            or bear.get("live_execution") is not False
            or bear.get("tradable_strategy_approved") is not False
            or bear.get("scenario_count") != 20
            or len(bear.get("scenario_results", [])) != 20
            or len(bear.get("per_year_market_coverage", [])) < 2):
        raise RuntimeError("BEAR_RESEARCH_GOVERNANCE_FAILED")

    # This forward journal must exist on every main-branch publish after
    # initialization. Verify SHA256, chain links, event counts and governance
    # independently of optional pandas/numpy research dependencies.
    future_root = r / "research" / "forward_shadow"
    evidence_files = ["journal.jsonl", "report.json", "snapshots.csv", "outcomes.csv"]
    if not all((future_root / name).is_file()
               and (future_root / name).stat().st_size > 10
               for name in evidence_files):
        raise RuntimeError("MISSING_SEALED_FORWARD_SHADOW_EVIDENCE")
    fwd = json.loads((future_root / "report.json").read_text())
    journal = (future_root / "journal.jsonl").read_bytes()
    if (fwd.get("version") != "daily20-forward-shadow-v1"
            or fwd.get("status") != "RESEARCH_ONLY"
            or fwd.get("research_only") is not True
            or fwd.get("live_execution") is not False
            or fwd.get("approved_live") is not False
            or fwd.get("historical_oos_2024_26_promoted") is not False
            or fwd.get("retrospective_backfill") is not False
            or fwd.get("last_completed_session") != qc["expected_session"]
            or hashlib.sha256(journal).hexdigest() != fwd.get("journal_sha256")):
        raise RuntimeError("FORWARD_SHADOW_PUBLISH_GOVERNANCE_FAILED")
    if os.environ.get("GITHUB_RUN_ID") and fwd.get("source_run_id") != os.environ["GITHUB_RUN_ID"]:
        raise RuntimeError("FORWARD_SHADOW_WRONG_ACTIONS_RUN")
    stream = [json.loads(line) for line in journal.decode("utf-8").splitlines()]
    last_hash = "0" * 64
    signals = settlements = 0
    for index, event in enumerate(stream, 1):
        expected = hashlib.sha256(json.dumps(
            {key: value for key, value in event.items() if key != "hash"},
            sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()).hexdigest()
        if (event.get("seq") != index or event.get("prev_hash") != last_hash
                or event.get("hash") != expected
                or event.get("research_only") is not True):
            raise RuntimeError("FORWARD_SHADOW_EVENT_CHAIN_BROKEN")
        if event.get("kind") == "SIGNAL":
            signals += 1
        elif event.get("kind") == "SETTLED":
            settlements += 1
        else:
            raise RuntimeError("INVALID_FORWARD_SHADOW_EVENT_TYPE")
        last_hash = event["hash"]
    if (signals < 20 or signals % 20
            or signals != fwd.get("signal_events")
            or settlements != fwd.get("settled_events")
            or signals - settlements != fwd.get("pending_events")
            or last_hash != fwd.get("journal_hash_tip")):
        raise RuntimeError("FORWARD_SHADOW_COUNTERS_INVALID")

    # Separate bear family forward evidence: journal cannot redefine a
    # historical baseline signal, family, candidate or realized outcome.
    bear_fwd_root = r / "research" / "bear_forward"
    bear_fwd_files = ("journal.jsonl", "report.json", "snapshots.csv",
                      "outcomes.csv", "latest_candidates.csv")
    if not all((bear_fwd_root / name).is_file()
               and (bear_fwd_root / name).stat().st_size > 10
               for name in bear_fwd_files):
        raise RuntimeError("BEAR_FORWARD_EVIDENCE_INCOMPLETE")
    bfw = json.loads((bear_fwd_root / "report.json").read_text())
    bear_bytes = (bear_fwd_root / "journal.jsonl").read_bytes()
    if (bfw.get("version") != "daily20-bear-forward-v1"
            or bfw.get("status") != "RESEARCH_ONLY"
            or bfw.get("research_only") is not True
            or bfw.get("live_execution") is not False
            or bfw.get("approved_live") is not False
            or bfw.get("historical_oos_promoted") is not False
            or bfw.get("backdated_signal_reconstruction") is not False
            or bfw.get("benchmark_model_not_modified") is not True
            or bfw.get("no_broker_order") is not True
            or bfw.get("last_completed_session") != qc["expected_session"]
            or bfw.get("source_run_id") != fwd.get("source_run_id")
            or hashlib.sha256(bear_bytes).hexdigest() != bfw.get("journal_sha256")):
        raise RuntimeError("BEAR_FORWARD_GOVERNANCE_INVALID")
    bear_events = [json.loads(line) for line in bear_bytes.decode().splitlines()]
    baseline_anchors = {
        (e["signal_date"], e["symbol"]): e["hash"]
        for e in stream if e["kind"] == "SIGNAL"
    }
    valid_core = {e["provider_symbol"] for e in universe["assets"]
                  if e["group"] == "DAILY20_CORE"}
    bear_signals, bear_settled = {}, set()
    per_day = {}
    prev = "0" * 64
    for n, e in enumerate(bear_events, 1):
        expected = hashlib.sha256(json.dumps(
            {key: value for key, value in e.items() if key != "hash"},
            sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()).hexdigest()
        if (e.get("seq") != n or e.get("prev_hash") != prev
                or e.get("hash") != expected
                or e.get("research_only") is not True
                or e.get("symbol") not in valid_core
                or e.get("family") not in ("BEAR_LOGISTIC", "BEAR_RULE")):
            raise RuntimeError("BEAR_FORWARD_CHAIN_INVALID")
        key = (e.get("signal_date"), e["symbol"], e["family"])
        if e["kind"] == "SIGNAL":
            if (key in bear_signals
                    or e.get("candidate") not in (True, False)
                    or type(e.get("candidate")) is not bool
                    or type(e.get("eligible")) is not bool
                    or (e["candidate"] and not e["eligible"])
                    or e.get("model_version") != "daily20-bear-forward-v1"
                    or e.get("baseline_signal_hash") != baseline_anchors.get(key[:2])
                    or not isinstance(e.get("feature_sha256"), str)
                    or len(e["feature_sha256"]) != 64):
                raise RuntimeError("BEAR_FORWARD_SIGNAL_ANCHOR_INVALID")
            prob = e.get("probability")
            if (e["family"] == "BEAR_RULE" and prob is not None
                    or e["family"] == "BEAR_LOGISTIC"
                    and e["candidate"] and (prob is None or not 0 <= prob <= 1)):
                raise RuntimeError("BEAR_FORWARD_MODEL_SCORE_INVALID")
            bear_signals[key] = e
            per_day.setdefault(key[0], set()).add(key[1:])
        elif e["kind"] == "SETTLED":
            if (key not in bear_signals or key in bear_settled
                    or e.get("signal_hash") != bear_signals[key]["hash"]
                    or e.get("observation_only_no_execution") is not True
                    or e.get("candidate_at_signal_time") != bear_signals[key]["candidate"]):
                raise RuntimeError("BEAR_FORWARD_SETTLEMENT_ANCHOR_INVALID")
            bear_settled.add(key)
        else:
            raise RuntimeError("BEAR_FORWARD_EVENT_KIND_INVALID")
        prev = e["hash"]
    expected_pairs = {
        (s, family) for s in valid_core
        for family in ("BEAR_LOGISTIC", "BEAR_RULE")
    }
    if (not per_day or any(pairs != expected_pairs for pairs in per_day.values())
            or len(bear_signals) != bfw.get("signal_events")
            or len(bear_settled) != bfw.get("settled_events")
            or len(bear_signals) - len(bear_settled) != bfw.get("pending_events")
            or len(per_day) != bfw.get("frozen_sessions")
            or len(bear_signals) != 40 * len(per_day)
            or bfw.get("journal_hash_tip") != prev):
        raise RuntimeError("BEAR_FORWARD_COUNTS_INCOMPLETE")
    if any(date > qc["expected_session"] or date < "2026-11-20" for date in per_day):
        raise RuntimeError("BEAR_FORWARD_FUTURE_OR_BACKDATED_SESSION")
    for family in ("BEAR_LOGISTIC", "BEAR_RULE"):
        f = [v for v in bear_signals.values() if v["family"] == family]
        reported = bfw.get("family", {}).get(family, {})
        if (len(f) != reported.get("signals")
                or sum(v["candidate"] for v in f) != reported.get("candidates")):
            raise RuntimeError("BEAR_FORWARD_FAMILY_COUNTS_MISMATCH")

    # Mandatory Monte Carlo: no publication if risk tails are absent or an
    # output is marked as forward validation or approved for live orders.
    mc_dir = r / "research" / "monte_carlo"
    mc_files = ["monte_carlo_summary.json", "monte_carlo_scenarios.csv",
                "monte_carlo_observed_baseline.csv"]
    if not all((mc_dir / file).is_file() and (mc_dir / file).stat().st_size > 10
               for file in mc_files):
        raise RuntimeError("MONTE_CARLO_EVIDENCE_INCOMPLETE")
    mc = json.loads((mc_dir / "monte_carlo_summary.json").read_text())
    if (mc.get("version") != "daily20-monte-carlo-v1"
            or mc.get("status") != "HISTORICAL_RESAMPLING_ONLY"
            or mc.get("research_only") is not True
            or mc.get("approved_live") is not False
            or mc.get("model_selection_allowed") is not False
            or mc.get("future_oos_validated") is not False
            or mc.get("not_a_forecast_probability") is not True
            or mc.get("sampling_method") != "paired_circular_moving_block_bootstrap_year_stratified"
            or mc.get("replications_per_block") != 2000
            or mc.get("block_lengths") != [1, 5, 20]
            or mc.get("strategy_scenarios") != 36
            or mc.get("benchmarks") != ["SPY", "QQQ"]
            or mc.get("scenario_rows") != 114
            or mc.get("sessions", 0) < 252
            or mc.get("last_session") != qc["expected_session"]
            or len(mc.get("primary_block20", [])) != 6):
        raise RuntimeError("MONTE_CARLO_GOVERNANCE_FAILED")
    import csv
    import math
    with (mc_dir / "monte_carlo_scenarios.csv").open(newline="") as infile:
        mc_rows = list(csv.DictReader(infile))
    if len(mc_rows) != 114:
        raise RuntimeError("MONTE_CARLO_ROWS_INCOMPLETE")
    mc_keys = set()
    for row in mc_rows:
        key = (row.get("scenario"), row.get("block_length"))
        if key in mc_keys or key[1] not in ("1", "5", "20"):
            raise RuntimeError("MONTE_CARLO_DUPLICATE_OR_INVALID_BLOCK")
        mc_keys.add(key)
        if row.get("n_resamples") != "2000" or row.get("status") != "HISTORICAL_RESAMPLING_ONLY" or row.get("approved_live") != "False":
            raise RuntimeError("MONTE_CARLO_NONAPPROVED_REPLICATION")
        for metric in ("loss_probability", "mdd_at_least_20pct_probability",
                       "mdd_at_least_30pct_probability",
                       "probability_underperform_spy", "probability_underperform_qqq"):
            try:
                p = float(row[metric])
            except (ValueError, TypeError, KeyError):
                raise RuntimeError("MONTE_CARLO_MISSING_PROBABILITY") from None
            if not math.isfinite(p) or not 0 <= p <= 1:
                raise RuntimeError("MONTE_CARLO_PROBABILITY_OUTSIDE_UNIT_INTERVAL")
        try:
            lo, mid, hi = [float(row[k]) for k in
                           ("return_p05", "return_median", "return_p95")]
            worst, median, best = [float(row[k]) for k in
                                   ("mdd_p05_worst", "mdd_median", "mdd_p95_best")]
        except (ValueError, TypeError, KeyError):
            raise RuntimeError("MONTE_CARLO_INVALID_QUANTILE") from None
        if (not all(map(math.isfinite, (lo, mid, hi, worst, median, best)))
                or not (lo <= mid <= hi and -1 <= worst <= median <= best <= 0)):
            raise RuntimeError("MONTE_CARLO_INVALID_TAIL_ORDER")
    if len({name for name, block in mc_keys if block == "20"}) != 38:
        raise RuntimeError("MONTE_CARLO_MISSING_PAIRED_SCENARIO")
    if not {"BENCHMARK_SPY", "BENCHMARK_QQQ"}.issubset(
        {name for name, block in mc_keys if block == "20"}
    ):
        raise RuntimeError("MONTE_CARLO_BENCHMARK_ABSENT")

    # Only accept complete 26+26 Parquet sources; no paths outside the unpacked Actions artifact.
    market_files = sorted((d / "market/raw/yfinance").glob("*.parquet"))
    feature_files = sorted((d / "features/talib").glob("*.parquet"))
    if len(market_files) != 26 or len(feature_files) != 26:
        raise RuntimeError(f"INCOMPLETE_PARQUET: raw={len(market_files)} features={len(feature_files)}")
    paths = [*market_files, *feature_files]
    if not all(p.is_file() and p.stat().st_size > 100 for p in paths):
        raise RuntimeError("EMPTY_PARQUET_FILE")
    expected_keys = {"yf_" + re.sub("[^a-z0-9]+", "_", x["provider_symbol"].lower()).strip("_")
                     for x in universe["assets"]}
    if set(p.stem for p in market_files) != expected_keys:
        raise RuntimeError("RAW_ASSET_KEYS_DO_NOT_MATCH_UNIVERSE")
    if len({x["symbol"] for x in qc.get("symbols", [])}) != 26:
        raise RuntimeError("QC_SYMBOL_KEYS_INCOMPLETE")

    manifest = {
        "format": "kalman-daily20-drive-v1",
        "research_only": True,
        "production_writes": False,
        "universe_version": summary.get("version"),
        "data_expected_last_closed_xnys": qc.get("expected_session"),
        "source_sha": os.environ.get("GITHUB_SHA", "local-test"),
        "source_actions_run_id": os.environ.get("GITHUB_RUN_ID", "local-test"),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_symbols": len(market_files),
        "feature_symbols": len(feature_files),
        "oos_trade_rows": summary.get("total_oos_trades"),
        "oos_score_count": summary.get("latest_score_count"),
        "portfolio_scenarios": portfolio["scenario_count"],
        "portfolio_mdd_available": True,
        "bear_oos_scenarios": bear["scenario_count"],
        "bear_oos_trade_rows": bear["unique_bear_oos_trades"],
        "prospective_signal_events": signals,
        "prospective_settled_events": settlements,
        "prospective_admitted_start": fwd["first_admitted_session"],
        "prospective_tip_hash": last_hash,
        "bear_forward_signals": len(bear_signals),
        "bear_forward_settled": len(bear_settled),
        "bear_forward_tip_hash": prev,
        "monte_carlo_scenarios": mc["strategy_scenarios"],
        "monte_carlo_block_lengths": mc["block_lengths"],
        "monte_carlo_repetitions": mc["replications_per_block"],
        "monte_carlo_approved_live": False,
    }
    return manifest


def build_zip(source_root, output_zip, manifest):
    root = Path(source_root).resolve()
    files = sorted(p for p in root.rglob("*") if p.is_file())
    if not files:
        raise RuntimeError("EMPTY_UPLOAD_PAYLOAD")
    output_zip = Path(output_zip)
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    per_file_hash = {}
    with ZipFile(output_zip, "w", ZIP_DEFLATED, compresslevel=6) as zipf:
        for p in files:
            if p.resolve() == output_zip.resolve() or root not in p.resolve().parents:
                continue
            relative = str(p.relative_to(root))
            zipf.write(p, relative)
            per_file_hash[relative] = sha256_file(p)
        mf = {**manifest, "payload_hashes_sha256": per_file_hash}
        zipf.writestr("drive_manifest.json", json.dumps(mf, indent=2))
    with ZipFile(output_zip) as z:
        if z.testzip() is not None or "drive_manifest.json" not in z.namelist():
            raise RuntimeError("ZIP_INTEGRITY_ERROR")
    return output_zip


def credentials_from_env():
    from google.oauth2 import service_account
    raw = os.environ.get("CKD_DRIVE_SA_JSON", "").strip()
    if not raw:
        value = os.environ.get("GDRIVE_SA_JSON_B64", "").strip()
        if value:
            raw = base64.b64decode(value, validate=True).decode("utf-8")
    if not raw:
        raise RuntimeError("GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_MISSING")
    data = json.loads(raw)
    if data.get("type") != "service_account" or data.get("client_email") != EXPECTED_SERVICE_ACCOUNT:
        raise RuntimeError("UNEXPECTED_SERVICE_ACCOUNT_IDENTITY")
    return service_account.Credentials.from_service_account_info(
        data, scopes=["https://www.googleapis.com/auth/drive"]
    )


def publish_one(service, kind, archive):
    from googleapiclient.http import MediaFileUpload
    target_id, target_name = EXPECTED_TARGETS[kind]
    current = service.files().get(
        fileId=target_id, fields="id,name,mimeType", supportsAllDrives=True
    ).execute()
    if current.get("name") != target_name or current.get("mimeType") != "application/zip":
        raise RuntimeError("DRIVE_TARGET_GUARD_FAILED_" + kind.upper())
    updated = service.files().update(
        fileId=target_id,
        media_body=MediaFileUpload(str(archive), mimetype="application/zip", resumable=True),
        fields="id,name,size,md5Checksum,modifiedTime",
        supportsAllDrives=True,
    ).execute()
    observed_md5 = updated.get("md5Checksum")
    if not observed_md5:
        meta = service.files().get(
            fileId=target_id, fields="id,name,size,md5Checksum,modifiedTime",
            supportsAllDrives=True
        ).execute()
        observed_md5 = meta.get("md5Checksum")
    if observed_md5 != md5_file(archive):
        raise RuntimeError("DRIVE_MD5_READBACK_MISMATCH_" + kind.upper())
    return {"kind": kind, "drive_file_id": target_id, "status": "VERIFIED",
            "size": updated.get("size"), "modified_at": updated.get("modifiedTime")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--results-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    manifest = inspect_payload(args.data_root, args.results_root)
    output = Path(args.output_root)
    data = build_zip(args.data_root, output / "daily20_data_latest.zip", manifest)
    results = build_zip(args.results_root, output / "daily20_results_latest.zip", manifest)
    print(json.dumps({"bundle_status": "VALIDATED",
                      "raw_symbols": manifest["raw_symbols"],
                      "feature_symbols": manifest["feature_symbols"],
                      "oos_scores": manifest["oos_score_count"],
                      "session": manifest["data_expected_last_closed_xnys"]}))
    if args.validate_only:
        return
    import googleapiclient.discovery
    service = googleapiclient.discovery.build(
        "drive", "v3", credentials=credentials_from_env(), cache_discovery=False
    )
    # Publish data first and results last, so reported results never precede new data.
    verified = [publish_one(service, "data", data),
                publish_one(service, "results", results)]
    print(json.dumps({"drive_upload": "COMPLETE", "files": verified}))


if __name__ == "__main__":
    main()
