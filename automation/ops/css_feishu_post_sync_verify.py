#!/usr/bin/env python3
"""Post-writer independent Feishu original→Google projection gate (read only).

Run immediately after the existing unified Feishu writer. A writer's own
readback does not prove that the original source still matches. Emit only
fixed labels and aggregate counts, never customer cell values or addresses.
"""
import datetime as dt
import json
import os
from pathlib import Path
import sys

from css_authenticated_original_probes import (
    live_feishu, sheets_session, summarized_feishu_drift_triage,
)

SOURCE_NAMES = ("Payment Outstanding", "Payment Receipt", "Prepayments", "eTax Invoice")


def evaluate(probe):
    """Only source+mirror exact parity is a snapshot PASS; never business PASS."""
    triage = summarized_feishu_drift_triage(probe)
    original_available = probe.get("source_probe") == "PASS_ORIGINAL_READ"
    mirror_matched = probe.get("mirror_projection_status") == "PASS"
    full_parity = original_available and mirror_matched and all(
        triage[name]["triage"] == "SNAPSHOT_MATCH_ONLY" for name in SOURCE_NAMES)
    return {
        "state": "PASS_SNAPSHOT_PROJECTION_ONLY" if full_parity else "SOURCE_MIRROR_HOLD",
        "source_probed": original_available,
        "projection_equal": full_parity,
        "formats": triage,
        "finance_authority_verified": False,
        "bank_receipt_verified": False,
        "sfdc_save_verified": False,
        "customer_data_writes": 0,
    }


def main():
    path = Path("audit-results/css-feishu-post-sync.json")
    path.parent.mkdir(exist_ok=True, parents=True)
    report = {"checked_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "state": "SOURCE_UNAVAILABLE", "projection_equal": False,
              "finance_authority_verified": False,
              "customer_data_writes": 0}
    try:
        report.update(evaluate(live_feishu(sheets_session())))
    except Exception as exc:
        # Public Action logs must never contain source/customer values or URLs.
        report["error_type"] = type(exc).__name__
    path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")
    print("FEISHU_POST_SYNC_PROOF " + json.dumps(report, ensure_ascii=False, sort_keys=True))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write("## Independent Feishu original→mirror post-write verification\n\n")
            out.write("State: **" + report["state"] + "** (snapshot only, never bank/payment proof)\n\n")
            out.write("| Format | Triage | Changed cells | Financial field cells | Status field cells |\n")
            out.write("|---|---|---:|---:|---:|\n")
            for name, item in report.get("formats", {}).items():
                out.write("| " + name + " | " + item["triage"] + " | " +
                          str(item["changed_cells"]) + " | " +
                          str(item["financial_field_cells"]) + " | " +
                          str(item["status_field_cells"]) + " |\n")
            out.write("\nUnverified is not zero. No original, invoice or payment data changed.\n")
    if report["state"] != "PASS_SNAPSHOT_PROJECTION_ONLY":
        print("::error title=Feishu post-write parity HOLD::Independent source/mirror comparison did not pass")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
