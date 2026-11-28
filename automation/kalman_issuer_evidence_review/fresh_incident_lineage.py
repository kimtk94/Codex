"""Fresh read-only issuer lineage recheck for the exact failed Daily20 session."""
import argparse
import json
from pathlib import Path, PurePosixPath
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "kalman_daily20"))
from issuer_qld2023_distribution_api import run as qld_run
from issuer_qqq2018_schedule import build_report as qqq_run
from issuer_ca_provider_reconciliation import run as lineage_run

from cache_rehearsal import CURRENT_PIN
from evidence_review import REPORT_SUFFIX, read_member, sha

LINEAGE = ROOT / "research" / "kalman_daily20" / "issuer_ca_secondary_vendor_lineage.json"
EXPECTED_EVENTS = {("QQQ", "2018-06-18"), ("QLD", "2023-09-20")}
VALID_QLD = {
    "ISSUER_API_2023_TARGET_ROW_ABSENT_HISTORY_HOLD",
    "ISSUER_API_2023_TARGET_ROW_PRESENT_CASH_UNCERTIFIED",
}

def require(condition, code):
    if not condition:
        raise ValueError(code)

def assert_hold(summary):
    require(summary.get("research_only") is True
            and summary.get("production_writes") is False
            and summary.get("strategy_promoted") is False
            and summary.get("cache_reuse_authorized") is False,
            "FRESH_LINEAGE_GOVERNANCE_HOLD")
    require(summary.get("issuer_payments_certified") == 0
            and summary.get("source_finality_verified") == 0,
            "FRESH_LINEAGE_CERTIFICATION_HOLD")
    require(summary.get("official_price_close_certified") == 0
            and summary.get("independent_adjustment_factor_certified") == 0,
            "FRESH_LINEAGE_PRICE_PROMOTION_HOLD")
    return summary

def extract_gap(archive):
    blob = Path(archive).read_bytes()
    require(sha(blob) == CURRENT_PIN, "INCIDENT_ARCHIVE_PIN_MISMATCH")
    with ZipFile(archive) as z:
        matches = [n for n in z.namelist()
                   if n == REPORT_SUFFIX or n.endswith("/" + REPORT_SUFFIX)]
        require(len(matches) == 1, "INCIDENT_REPORT_PATH_AMBIGUOUS")
        prefix = PurePosixPath(matches[0]).parent
        name = str(prefix.parent / "issuer_ca_gap_audit.json")
        gap = json.loads(read_member(z, name, 2_000_000))
    require(gap.get("status") == "ISSUER_DISTRIBUTIONS_2_EVENTS_HOLD"
            and gap.get("research_only") is True
            and gap.get("production_writes") is False
            and gap.get("strategy_promoted") is False
            and gap.get("issuer_payments_certified") == 0
            and gap.get("source_finality_verified") == 0,
            "INCIDENT_GAP_GOVERNANCE_HOLD")
    events = {(e.get("symbol"), e.get("ex_date")) for e in gap.get("events", [])}
    require(events == EXPECTED_EVENTS, "INCIDENT_GAP_EVENT_SET_HOLD")
    return gap, sha(json.dumps(gap, sort_keys=True).encode())

def run(incident_archive, out_dir):
    gap, gap_sha = extract_gap(incident_archive)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        qld_dir, qqq_dir = root / "qld", root / "qqq"
        qld_dir.mkdir()
        qqq_dir.mkdir()
        qld = qld_run(out_dir=qld_dir)
        qqq = qqq_run(outdir=qqq_dir)
        (qld_dir / "report.json").write_text(
            json.dumps(qld, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (qqq_dir / "report.json").write_text(
            json.dumps(qqq, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        provider = None
        if qld.get("source_sha256") and qld.get("status") not in VALID_QLD:
            provider_status = "QLD_SOURCE_CAPTURED_SCHEMA_REJECTED_HOLD"
        else:
            provider = lineage_run(json.loads(LINEAGE.read_text(encoding="utf-8")),
                                   gap, qld_dir, qqq_dir)
            provider_status = provider.get("status")
        summary = {
            "version": "daily20-fresh-issuer-lineage-recheck-v1",
            "status": "FRESH_SOURCE_REVIEW_HOLD",
            "incident_archive_sha256": CURRENT_PIN,
            "incident_gap_sha256": gap_sha,
            "incident_session": "2026-11-27",
            "fresh_check_time_utc": datetime.now(timezone.utc).isoformat(),
            "qld_api_status": qld.get("status"),
            "qld_api_source_sha256": qld.get("source_sha256"),
            "qld_api_rows": qld.get("api_2023_row_count"),
            "qld_target_row_present": qld.get("issuer_api_target_row") is not None,
            "qld_fetch_error_code": qld.get("fetch_error_code"),
            "qqq_schedule_status": qqq.get("status"),
            "qqq_schedule_source_sha256": qqq.get("source_sha256"),
            "qqq_schedule_anchor_verified": qqq.get("source_anchor_verified") is True,
            "qqq_fetch_error_type": qqq.get("fetch_error_type"),
            "provider_reconciliation_status": provider_status,
            "provider_reconciliation": provider,
            "research_only": True, "production_writes": False,
            "strategy_promoted": False, "cache_reuse_authorized": False,
            "issuer_payments_certified": 0, "source_finality_verified": 0,
            "official_price_close_certified": 0,
            "independent_adjustment_factor_certified": 0,
        }
        assert_hold(summary)
        (out / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        import shutil
        shutil.copytree(qld_dir, out / "qld", dirs_exist_ok=True)
        shutil.copytree(qqq_dir, out / "qqq", dirs_exist_ok=True)
    return summary

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("incident_archive")
    p.add_argument("--out-dir", required=True)
    a = p.parse_args()
    print(json.dumps(run(a.incident_archive, a.out_dir), sort_keys=True))
