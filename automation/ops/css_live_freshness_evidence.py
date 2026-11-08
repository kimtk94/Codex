#!/usr/bin/env python3
"""Read-only, fail-closed CSS freshness evidence snapshot.

The input is the operational Google Sheet *mirror*, not the original QQ/CRM,
Salesforce or Feishu API. Mirror observations are NEVER promoted to authenticated
source or destination PASS. This report makes missing live proof explicit.
"""
import base64
import datetime as dt
import json
import os
from pathlib import Path
import sys

from css_freshness_policy import POLICY_FILE, validate_policy

BOOK = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TABS = {
    "Feishu Source Manifest": "A1:G12",
    "SFDC Email Ingest Audit": "A1:J10",
    "SFDC Report Readiness": "A1:H10",
    "Revenue Source Authority": "A1:J25",
    "BI Revenue Net VAT Monthly": "A1:I25",
    "Payment Reconciliation QC": "A1:C35",
    "Automation Workflow Runs": "A1:J45",
    "CSS Mail Backfill Status": "A1:L3",
}
SENSITIVE = frozenset({"From", "Subject", "Email", "Customer", "Contact"})


def cell(row, index):
    return str(row[index]).strip() if index < len(row) and row[index] is not None else ""


def rows_for(data, name, minimum_columns):
    rows = data.get(name)
    if not isinstance(rows, list) or not rows or len(rows[0]) < minimum_columns:
        raise ValueError("MIRROR_TAB_MISSING_OR_TRUNCATED:" + name)
    return rows


def find_key(rows, key, column=0):
    found = [r for r in rows[1:] if cell(r, column) == key]
    if len(found) != 1:
        raise ValueError("MIRROR_KEY_MISSING_OR_DUPLICATE:" + key)
    return found[0]


def month_gross_net(authority, net_table, month):
    gross_row = find_key([authority[0]] + [r for r in authority[1:]
        if cell(r, 2) == "CANONICAL_ACTUAL_GROSS"], month)
    net_row = find_key([authority[0]] + [r for r in authority[1:]
        if cell(r, 2) == "CANONICAL_ISSUED_NET"], month)
    monthly = find_key(net_table, month)
    gross = int(cell(gross_row, 4))
    net = int(cell(net_row, 4))
    count = int(cell(gross_row, 3))
    actual_count = int(cell(monthly, 4))
    # All values are integer KRW; avoid floating-point VAT drift.
    parity = (gross * 10 == net * 11 and
        gross == int(cell(monthly, 1)) and
        net == int(cell(monthly, 2)) and
        count == int(cell(net_row, 3)) == actual_count and
        cell(gross_row, 5) == "VAT_INCLUDED" and
        cell(net_row, 5) == "VAT_EXCLUDED" and
        cell(gross_row, 7) == cell(net_row, 7) == "YES")
    return {"month": month, "invoice_count": count,
            "gross_vat_included_krw": gross, "net_vat_excluded_krw": net,
            "snapshot_amount_parity": parity}


def observe(data, now, target_month=None):
    """Return two independent *pending* source/sink observations per domain.

    Do not confuse a successfully queried mirror with the actual source probe.
    """
    policy = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    validate_policy(policy)
    manifest = rows_for(data, "Feishu Source Manifest", 7)
    ingest = rows_for(data, "SFDC Email Ingest Audit", 10)
    readiness = rows_for(data, "SFDC Report Readiness", 8)
    authority = rows_for(data, "Revenue Source Authority", 10)
    monthly = rows_for(data, "BI Revenue Net VAT Monthly", 9)
    payment = rows_for(data, "Payment Reconciliation QC", 3)
    workflows = rows_for(data, "Automation Workflow Runs", 10)
    backfill = rows_for(data, "CSS Mail Backfill Status", 10)
    target_month = target_month or now.astimezone(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m")
    findings = {}
    for name in ("Payment Outstanding", "eTax Invoice", "Payment Receipt", "Prepayments", "Online-Project"):
        row = find_key(manifest, name)
        date, sync, count = cell(row, 1), cell(row, 2), cell(row, 4)
        findings[name] = {
            "source_date": date, "mirror_sync_at": sync,
            "snapshot_rows": int(count) if count.isdigit() else None,
            "source_month_matches_target": date.startswith(target_month),
        }
    report_sources = {}
    for key in ("Leads", "Opportunities", "Quotation"):
        row = find_key(ingest, key)
        report_sources[key] = {
            "source_received_kst": cell(row, 1),
            "ingest_checked_kst": cell(row, 2),
            "staged_rows": int(cell(row, 3)),
            "unique_ids": int(cell(row, 4)),
            "missing_ids": int(cell(row, 6)),
            "stage_state": cell(row, 8),
        }
    sfdc_gates = {}
    for row in readiness[1:]:
        key = cell(row, 0)
        if key:
            sfdc_gates[key] = {
                "stable_id": cell(row, 2), "modified_timestamp": cell(row, 3),
                "field_check": cell(row, 4), "promotion_status": cell(row, 6),
            }
    rev = month_gross_net(authority, monthly, target_month)
    metrics = {cell(r, 0): cell(r, 1) for r in payment[2:] if cell(r, 0)}
    run_results = {
        cell(r, 9): cell(r, 2) for r in workflows[1:] if cell(r, 9)
    }
    cache = backfill[1] if len(backfill) > 1 else []
    notes = {
        "mail": {
            "source": {"mirror_headers": int(cell(cache, 2)) if cell(cache, 2).isdigit() else None,
                       "cached_uid": int(cell(cache, 3)) if cell(cache, 3).isdigit() else None},
            "sink": {"mirror_cache_status": cell(cache, 1), "body_ready": cell(cache, 4),
                     "remaining_eligible": cell(cache, 7)},
        },
        "lead": {
            "source": {"staged_report": report_sources["Leads"]},
            "sink": {"sfdc_raw_gate": sfdc_gates.get("SFDC Contacts"),
                     "reason": "SFDC_CONTACT_READBACK_NOT_AUTHENTICATED"},
        },
        "quote": {
            "source": {"opportunities": report_sources["Opportunities"],
                       "quotations": report_sources["Quotation"]},
            "sink": {"sfdc_raw_gate": sfdc_gates.get("SFDC Opportunity Raw"),
                     "quotation_gate": sfdc_gates.get("Quotation"),
                     "reason": "SFDC_SAVE_NOT_VERIFIED"},
        },
        "contract_po": {
            "source": {"reason": "OWNER_QQ_ORIGINAL_CONTRACT_PROBE_NOT_IN_THIS_AUDIT"},
            "sink": {"reason": "FEISHU_PO_FILE_READBACK_NOT_IN_THIS_AUDIT"},
        },
        "sif_project": {
            "source": {"online_project": findings["Online-Project"]},
            "sink": {"reason": "PROJECT_STAGE_ORIGINAL_VS_SINK_KEY_PARITY_NOT_VERIFIED"},
        },
        "invoice": {
            "source": {"reason": "PERSONAL_QQ_ORIGINAL_TAX_INVOICE_PROBE_NOT_IN_THIS_AUDIT"},
            "sink": {"reason": "PER_INVOICE_ATTACHMENT_AND_FEISHU_READBACK_NOT_VERIFIED"},
        },
        "payment_revenue": {
            "source": {"payment_outstanding": findings["Payment Outstanding"],
                       "payment_receipt": findings["Payment Receipt"],
                       "etax": findings["eTax Invoice"],
                       "paid_invoice_proof": metrics.get("Invoice-level verified paid count", "UNKNOWN")},
            "sink": {"monthly_snapshot": rev,
                     "reason": "FEISHU_MONTHLY_LIVE_READBACK_AND_RECEIPT_NOT_CERTIFIED"},
        },
        "feishu_bi": {
            "source": {"quote_and_invoice_watermarks": "ORIGINALS_NOT_PROBED",
                       "monthly_snapshot": rev},
            "sink": {"reason": "NATIVE_FEISHU_KPI_CARD_LIVE_READBACK_NOT_PROBED"},
        },
        "monitor": {
            "source": {"workflow_execution_only": run_results,
                       "reason": "WORKFLOW_SUCCESS_IS_NOT_SOURCE_FRESHNESS"},
            "sink": {"reason": "BUSINESS_READBACK_STATUS_LEDGER_NOT_PROVEN"},
        },
    }
    checked = now.isoformat()
    result = []
    for item in policy["domains"]:
        k = item["id"]
        evidence = []
        for axis in ("source", "sink"):
            e = {"axis": axis, "status": "BLOCK",
                 "reason": "MIRROR_SNAPSHOT_ONLY_NOT_ORIGINAL_PROOF",
                 "snapshot": notes[k][axis],
                 "source_event_at": None, "source_probe_at": None,
                 "ingest_at": None, "sink_readback_at": None,
                 "verified_at": checked, "source_identity": None,
                 "source_count": None, "sink_count": None,
                 "gap_count": None, "source_ref": None,
                 "sink_ref": None, "run_url": os.environ.get("GITHUB_SERVER_URL", "https://github.com")
                   + "/" + os.environ.get("GITHUB_REPOSITORY", "kimtk94/Codex")
                   + "/actions/runs/" + os.environ.get("GITHUB_RUN_ID", "0")}
            if k == "payment_revenue" and axis == "sink" and not rev["snapshot_amount_parity"]:
                e["reason"] = "CANONICAL_REVENUE_SNAPSHOT_MISMATCH"
            if k in ("lead", "quote") and axis == "sink":
                e["reason"] = "SFDC_STAGING_NOT_VERIFIED_SAVED"
            if k == "payment_revenue" and axis == "source" and (
                    not findings["eTax Invoice"]["source_month_matches_target"]):
                e["reason"] = "ETAX_SNAPSHOT_MONTH_NOT_TARGET_MONTH"
            evidence.append(e)
        result.append({"id": k, "name": item["name"],
                       "status": "BLOCK", "checks": evidence})
    return {"version": policy["policy_version"], "checked_at": checked,
            "target_month": target_month, "mirror_only": True,
            "source_probed_live": False, "sink_readback_live": False,
            "domains": result, "blocked_domains": len(result),
            "verified_crosschecks": 0,
            "note": "Mirror telemetry; independent QQ/SFDC/Feishu source probes and sink readbacks required."}


def google_values():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    raw = os.environ.get("CKD_DRIVE_SA_JSON")
    if not raw:
        raise RuntimeError("SHEETS_READ_CREDENTIALS_UNAVAILABLE")
    try:
        info = json.loads(raw)
    except ValueError:
        info = json.loads(base64.b64decode(raw))
    creds = service_account.Credentials.from_service_account_info(info,
         scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session = AuthorizedSession(creds)
    url = "https://sheets.googleapis.com/v4/spreadsheets/" + BOOK + "/values:batchGet"
    pairs = [("'" + key.replace("'", "''") + "'!" + a1, key)
             for key, a1 in TABS.items()]
    response = session.get(url, params=[("ranges", rng) for rng, _ in pairs], timeout=45)
    response.raise_for_status()
    data = response.json().get("valueRanges", [])
    if len(data) != len(pairs):
        raise RuntimeError("INCOMPLETE_SHEETS_MIRROR_READ")
    return {key: d.get("values", []) for (_, key), d in zip(pairs, data)}


def main():
    now = dt.datetime.now(dt.timezone.utc)
    report = observe(google_values(), now)
    path = Path("audit-results/css-live-freshness-evidence.json")
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    line = ("CSS_FRESHNESS_MIRROR_AUDIT_COMPLETE=YES DOMAINS=9 CROSSCHECKS=18 " +
            "LIVE_SOURCE_SINK_CERTIFIED=0 STATUS=BLOCK SOURCE_MIRROR_ONLY")
    print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write("## CSS source/sink freshness — evidence only\n\n")
            out.write("Mirror snapshot read: PASS. Independent original source probes: NOT DONE. " +
                      "Live destination readbacks: NOT DONE. **No business PASS.**\n\n")
            out.write("| Domain | Source | Sink | Business status |\n|---|---|---|---|\n")
            for item in report["domains"]:
                out.write("| " + item["name"] + " | BLOCK | BLOCK | BLOCK |\n")
            out.write("\nSee artifact `css-live-freshness-evidence` for snapshot counts/reasons.\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Keep source access failures distinct from a successfully observed zero delta.
        print("CSS_LIVE_FRESHNESS_EVIDENCE_FAILED=" + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
