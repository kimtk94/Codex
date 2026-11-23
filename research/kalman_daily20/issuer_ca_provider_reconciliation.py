#!/usr/bin/env python3
"""Reconcile two CA disputes by source lineage; research-only, fail closed.

Only archived issuer-origin bytes may be called source-verified. Curated
third-party observations are published claims, not original vendor records.
Issuer API omission is *not* historical nonpayment proof. Never amend prices.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import gzip
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlparse

from issuer_qld2023_distribution_api import inspect as inspect_qld
from issuer_qqq2018_schedule import verify_document as verify_qqq

SCHEMA = "daily20-ca-secondary-vendor-lineage-v1"
VERSION = "daily20-ca-vendor-lineage-reconciliation-v1"
TARGETS = {("QLD", "2023-09-20"), ("QQQ", "2018-06-18")}
PUBLISHERS = {
    "etfiq.com": "Tiingo",
    "stockanalysis.com": "S&P Global Market Intelligence",
    "app.tiingo.com": "Tiingo",
}
_ALLOWED_BASIS = {
    "ORIGINAL_2023_SHARES_CANDIDATE",
    "AFTER_2025_SPLIT_CANDIDATE",
    "2018_SHARES_CANDIDATE",
}

def decimal(value):
    if value in (None, ""):
        return None
    try:
        v = Decimal(str(value))
        return v if v.is_finite() and v >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None

def validate_claims(config):
    if config.get("schema") != SCHEMA or config.get("research_only") is not True:
        raise ValueError("CA_LINEAGE_SCHEMA_GOVERNANCE_INVALID")
    cases = {}
    observed_ids = set()
    for case in config.get("cases", []):
        key = (case.get("symbol"), case.get("ex_date"))
        if key not in TARGETS or key in cases:
            raise ValueError("CA_LINEAGE_CASE_INVALID")
        observations = case.get("observations")
        if not isinstance(observations, list) or not observations:
            raise ValueError("CA_LINEAGE_OBSERVATIONS_EMPTY")
        for obs in observations:
            sid = obs.get("id")
            if not isinstance(sid, str) or not sid.startswith(key[0] + "_") or sid in observed_ids:
                raise ValueError("CA_LINEAGE_OBSERVATION_ID_INVALID")
            observed_ids.add(sid)
            url = urlparse(obs.get("url", ""))
            if (url.scheme != "https" or url.hostname not in PUBLISHERS
                    or url.username or url.password or url.query or url.fragment):
                raise ValueError("CA_LINEAGE_PUBLISHER_URL_NOT_ALLOWLISTED")
            if obs.get("attributed_upstream") != PUBLISHERS[url.hostname]:
                raise ValueError("CA_LINEAGE_UPSTREAM_MISATTRIBUTED")
            if (obs.get("source_class") not in ("THIRD_PARTY_VENDOR", "THIRD_PARTY_VENDOR_DERIVED")
                    or obs.get("claim_status") != "PUBLISHED_CANDIDATE_NOT_ORIGINAL_ISSUER_CERTIFIED"
                    or obs.get("amount_basis") not in _ALLOWED_BASIS
                    or decimal(obs.get("displayed_amount_usd")) is None):
                raise ValueError("CA_LINEAGE_UNCERTIFIED_VENDOR_OBSERVATION_INVALID")
        cases[key] = observations
    if set(cases) != TARGETS:
        raise ValueError("CA_LINEAGE_CASE_COVERAGE_INVALID")
    return cases

def read_report(directory):
    path = Path(directory) / "report.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

def archive_bytes(folder, report, *, allowed_names):
    if not report.get("source_sha256"):
        return None, "SOURCE_NOT_ARCHIVED_RESEARCH_HOLD"
    name = report.get("source_archive")
    if (not isinstance(name, str) or name not in allowed_names
            or "/" in name or "\\" in name):
        raise ValueError("CA_LINEAGE_ARCHIVE_PATH_INVALID")
    path = Path(folder) / name
    if not path.is_file():
        raise ValueError("CA_LINEAGE_SOURCE_ARCHIVE_MISSING")
    data = gzip.decompress(path.read_bytes())
    if len(data) > 2_000_000 or sha256(data).hexdigest() != report["source_sha256"]:
        raise ValueError("CA_LINEAGE_SOURCE_SHA256_MISMATCH")
    return data, "ARCHIVED_ORIGINAL_BYTES_HASH_VERIFIED"

def run(secondary_manifest, gap, qld_directory, qqq_directory):
    claims = validate_claims(secondary_manifest)
    if not (gap.get("research_only") is True
            and gap.get("production_writes") is False
            and gap.get("source_finality_verified") == 0
            and gap.get("issuer_payments_certified") == 0):
        raise ValueError("CA_LINEAGE_UPSTREAM_GAP_NOT_FAIL_CLOSED")
    upstream = {(x.get("symbol"), x.get("ex_date")): x for x in gap.get("events", [])}
    if set(upstream) != TARGETS:
        raise ValueError("CA_LINEAGE_GAP_KEYS_INVALID")
    if any(upstream[k].get("actual_payment_certified") is not False for k in TARGETS):
        raise ValueError("CA_LINEAGE_PAYMENT_PROMOTED_UNEXPECTEDLY")
    qld_report, qqq_report = read_report(qld_directory), read_report(qqq_directory)
    qld_bytes, qld_grade = archive_bytes(qld_directory, qld_report,
        allowed_names={"qld_2023_proshares_api_raw_response.bin.gz"})
    qqq_bytes, qqq_grade = archive_bytes(qqq_directory, qqq_report,
        allowed_names={"qqq_2018_amendment_6_original.html.gz"})
    qld_rows = None
    qld_target = None
    if qld_bytes is not None:
        qld_rows, qld_target = inspect_qld(qld_bytes)
        if (qld_report.get("status") not in (
            "ISSUER_API_2023_TARGET_ROW_ABSENT_HISTORY_HOLD",
            "ISSUER_API_2023_TARGET_ROW_PRESENT_CASH_UNCERTIFIED"
        ) or qld_report.get("api_2023_row_count") != len(qld_rows)
                or qld_report.get("api_ex_dates") != sorted(x["ex_date"] for x in qld_rows)
                or bool(qld_report.get("issuer_api_target_row")) != bool(qld_target)):
            raise ValueError("CA_LINEAGE_QLD_API_REPORT_DISAGREES_WITH_BYTES")
    if qqq_bytes is not None:
        facts = verify_qqq(qqq_bytes)
        if not facts["source_anchor_verified"] or qqq_report.get("source_anchor_verified") is not True:
            raise ValueError("CA_LINEAGE_2018_ISSUER_RULE_ANCHOR_INVALID")
        if qqq_report.get("rule_derived_ex_date") != "2018-06-18":
            raise ValueError("CA_LINEAGE_2018_DATE_RULE_INVALID")
    if (qld_report.get("issuer_payment_finality_certified") is not False
            or qld_report.get("historical_nonpayment_proven") is not False
            or qqq_report.get("issuer_cash_payment_certified") is not False):
        raise ValueError("CA_LINEAGE_SOURCE_CLAIMS_EXCEED_SUPPORT")

    qld_claims = claims[("QLD","2023-09-20")]
    by_lineage = {x["attributed_upstream"]: x for x in qld_claims}
    if set(by_lineage) != {"Tiingo", "S&P Global Market Intelligence"}:
        raise ValueError("CA_LINEAGE_QLD_EXPECTED_UPSTREAM_MISSING")
    a = decimal(by_lineage["Tiingo"]["displayed_amount_usd"])
    b = decimal(by_lineage["S&P Global Market Intelligence"]["displayed_amount_usd"])
    split = decimal(upstream["QLD","2023-09-20"].get("split_new_shares_per_old"))
    split_reconciles = (split == Decimal("2") and a is not None and b is not None
                        and abs(a / split - b) <= Decimal("0.000005"))
    qld = {
        "symbol": "QLD", "ex_date": "2023-09-20",
        "issuer_api_source_sha256": qld_report.get("source_sha256"),
        "issuer_api_source_status": qld_report.get("status", "NOT_AVAILABLE"),
        "issuer_archive_grade": qld_grade,
        "issuer_api_2023_rows_revalidated": len(qld_rows) if qld_rows is not None else None,
        "issuer_api_2023_ex_dates": sorted(x["ex_date"] for x in qld_rows) if qld_rows is not None else None,
        "issuer_api_has_target_row": bool(qld_target) if qld_rows is not None else None,
        "historical_nonpayment_proven": False,
        "third_party_claims": qld_claims,
        "upstream_lineages_visible": sorted(by_lineage),
        "upstream_feed_independence_certified": False,
        "third_party_raw_2023_candidate_usd": str(a),
        "third_party_adjusted_2025_candidate_usd": str(b),
        "split_math_reconciles_to_publisher_precision": split_reconciles,
        "issuer_cash_payment_certified": False,
        "issuer_adjustment_factor_certified": False,
        "status": ("ISSUER_API_2023_MISSING_VS_SECONDARY_CANDIDATE_HOLD"
                   if qld_rows is not None and qld_target is None
                   else "ISSUER_API_2023_PRESENT_BUT_PAYMENT_UNCERTIFIED_HOLD"
                   if qld_target is not None else "ISSUER_API_NOT_CAPTURED_HOLD"),
    }

    qqq = {
        "symbol": "QQQ", "ex_date": "2018-06-18",
        "issuer_2018_schedule_source_sha256": qqq_report.get("source_sha256"),
        "issuer_2018_schedule_archive_grade": qqq_grade,
        "issuer_2018_schedule_rule_verified": qqq_bytes is not None,
        "issuer_2018_paid_cash_certified": False,
        "third_party_claims": claims["QQQ","2018-06-18"],
        "third_party_quote_usd": upstream["QQQ","2018-06-18"].get("sec_2020_third_party_2018_q3_quote_usd"),
        "alpaca_rate_usd": upstream["QQQ","2018-06-18"].get("alpaca_2018_event_candidate_usd"),
        "issuer_quote_minus_alpaca_usd": upstream["QQQ","2018-06-18"].get("sec_quote_minus_alpaca_usd"),
        "source_cash_amount_certified": False,
        "status": "ISSUER_2018_DATE_RULE_ONLY_CASH_CANDIDATES_CONFLICT_HOLD",
    }
    return {
        "version": VERSION, "research_only": True, "production_writes": False,
        "strategy_promoted": False, "issuer_distribution_payments_certified": 0,
        "source_finality_verified_assets": 0,
        "source_claim_grade": "UNCERTIFIED_VENDOR_CANDIDATES",
        "publisher_rows_are_directly_archived": False,
        "issuer_api_absence_never_implies_historical_nonpayment": True,
        "status": "TWO_CORPORATE_ACTION_SOURCE_DISAGREEMENTS_HOLD",
        "cases": [qqq,qld],
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--lineage",default="research/kalman_daily20/issuer_ca_secondary_vendor_lineage.json")
    p.add_argument("--gap",default="output/daily20/research/issuer_ca_gap_audit.json")
    p.add_argument("--qld-dir",default="output/daily20/research/issuer_qld2023_api")
    p.add_argument("--qqq-dir",default="output/daily20/research/issuer_qqq2018_rule")
    p.add_argument("--out",default="output/daily20/research/issuer_ca_provider_reconciliation.json")
    args=p.parse_args()
    report=run(json.loads(Path(args.lineage).read_text()),json.loads(Path(args.gap).read_text()),
               args.qld_dir,args.qqq_dir)
    dest=Path(args.out)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print("DAILY20_CA_VENDOR_LINEAGE",report["status"],
          [(x["symbol"],x["status"]) for x in report["cases"]],"CERTIFIED 0/26 HOLD")
if __name__=="__main__":
    main()
