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
