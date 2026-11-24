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
import re
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
    "BI Revenue Lifecycle Monthly": "A1:P25",
    "Automation Health": "A1:D50",
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


def _nonnegative_krw(value):
    """Parse exact whole KRW; never accept a float, guess, or blank as zero."""
    raw = str(value).strip().replace(",", "").replace("₩", "").replace(" ", "")
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)", raw):
        raise ValueError("REVENUE_MIRROR_AMOUNT_INVALID")
    return int(raw)


def relative_snapshot_order(net_stamp, lifecycle_stamp):
    """Compare explicitly dated KST mirror snapshots; not a causal diagnosis."""
    def parse(value):
        try:
            return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S KST")
        except (TypeError, ValueError):
            return None
    net_at = parse(net_stamp)
    life_at = parse(lifecycle_stamp)
    if net_at is None or life_at is None:
        return "UNVERIFIED_TIMESTAMPS"
    if life_at > net_at:
        return "LIFECYCLE_NEWER_THAN_NET"
    if net_at > life_at:
        return "NET_NEWER_THAN_LIFECYCLE"
    return "SAME_TIMESTAMP"


def month_gross_net(authority, net_table, month, lifecycle=None):
    gross_row = find_key([authority[0]] + [r for r in authority[1:]
        if cell(r, 2) == "CANONICAL_ACTUAL_GROSS"], month)
    net_row = find_key([authority[0]] + [r for r in authority[1:]
        if cell(r, 2) == "CANONICAL_ISSUED_NET"], month)
    monthly = find_key(net_table, month)
    gross = _nonnegative_krw(cell(gross_row, 4))
    net = _nonnegative_krw(cell(net_row, 4))
    count = _nonnegative_krw(cell(gross_row, 3))
    actual_count = _nonnegative_krw(cell(monthly, 4))
    monthly_gross = _nonnegative_krw(cell(monthly, 1))
    monthly_net = _nonnegative_krw(cell(monthly, 2))
    # Historical per-invoice VAT rounding can cause small gross/net differences.
    # Preserve the established 10/11 parity contract of this read-only audit.
    parity = (gross * 10 == net * 11 and
        gross == monthly_gross and net == monthly_net and
        count == _nonnegative_krw(cell(net_row, 3)) == actual_count and
        cell(gross_row, 5) == "VAT_INCLUDED" and
        cell(net_row, 5) == "VAT_EXCLUDED" and
        cell(gross_row, 7) == cell(net_row, 7) == "YES")
    result = {"month": month, "invoice_count": count,
              "snapshot_amount_parity": parity}
    if lifecycle is not None:
        life = find_key(lifecycle, month)
        life_gross = _nonnegative_krw(cell(life, 1))
        life_count = _nonnegative_krw(cell(life, 5))
        result.update({
            "lifecycle_invoice_count": life_count,
            "invoice_count_delta_lifecycle_minus_net": life_count - actual_count,
            "lifecycle_gross_differs_from_net": life_gross != monthly_gross,
            "net_snapshot_at": cell(monthly, 7),
            "lifecycle_snapshot_at": cell(life, 11),
            "snapshot_order": relative_snapshot_order(cell(monthly, 7), cell(life, 11)),
            "invoice_identity_review_required": (life_gross != monthly_gross or
                                                life_count != actual_count),
        })
        result["snapshot_amount_parity"] = (
            parity and life_gross == gross and life_count == count)
    # Public CI evidence contains only aggregates/flags, not monetary values.
    return result


def legacy_health_observation(rows, now, max_age_hours=48):
    """An old legacy PASS is NOT proof that a system is currently healthy."""
    if rows[0][:4] != ["Component", "Last success KST", "State", "Detail"]:
        raise ValueError("LEGACY_HEALTH_SCHEMA_INVALID")
    if now.tzinfo is None:
        raise ValueError("HEALTH_CLOCK_TZ_REQUIRED")
    kst = dt.timezone(dt.timedelta(hours=9))
    now_kst = now.astimezone(kst)
    counts = {"legacy_green_rows": 0, "stale_green_rows": 0,
              "unknown_timestamp_green_rows": 0,
              "legacy_green_is_current_proof": False}
    for row in rows[1:]:
        if cell(row, 2) not in ("PASS", "PASS_VERIFIED"):
            continue
        counts["legacy_green_rows"] += 1
        try:
            stamp = dt.datetime.strptime(
                cell(row, 1), "%Y-%m-%d %H:%M:%S KST").replace(tzinfo=kst)
        except ValueError:
            counts["unknown_timestamp_green_rows"] += 1
            continue
        age = now_kst - stamp
        if age < dt.timedelta(0) or age > dt.timedelta(hours=max_age_hours):
            counts["stale_green_rows"] += 1
    return counts


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
    lifecycle = rows_for(data, "BI Revenue Lifecycle Monthly", 12)
    health = rows_for(data, "Automation Health", 4)
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
    rev = month_gross_net(authority, monthly, target_month, lifecycle)
    legacy_health = legacy_health_observation(health, now)
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
                       "legacy_health": legacy_health,
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
            if k == "monitor" and axis == "source" and (
                    legacy_health["stale_green_rows"] or
                    legacy_health["unknown_timestamp_green_rows"]):
                e["reason"] = "LEGACY_HEALTH_GREEN_STATUS_NOT_CURRENT"
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
            "snapshot_integrity": {"revenue": rev, "legacy_health": legacy_health},
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
    health = report["snapshot_integrity"]["legacy_health"]
    revenue_ok = report["snapshot_integrity"]["revenue"]["snapshot_amount_parity"]
    if not revenue_ok:
        print("::warning title=Revenue snapshot mismatch::Lifecycle/Net VAT/Authority mirror parity is not established")
        # Count and order are evidence for triage, never permission to rewrite.
        snapshot = report["snapshot_integrity"]["revenue"]
        print("REVENUE_SNAPSHOT_HOLD month=" + snapshot["month"] +
              " invoice_count_delta_lifecycle_minus_net=" +
              str(snapshot.get("invoice_count_delta_lifecycle_minus_net")) +
              " order=" + snapshot.get("snapshot_order", "UNVERIFIED") +
              " source_invoice_identity_review=REQUIRED")

    if health["stale_green_rows"] or health["unknown_timestamp_green_rows"]:
        print("::warning title=Legacy Health stale PASS::Old PASS labels are not live certification")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write("## CSS source/sink freshness — evidence only\n\n")
            out.write("Mirror snapshot read: PASS. Independent original source probes: NOT DONE. " +
                      "Live destination readbacks: NOT DONE. **No business PASS.**\n\n")
            out.write("Revenue Net VAT/Lifecycle/Authority parity: **" +
                      ("MATCH" if revenue_ok else "MISMATCH / HOLD") + "**; "
                      "Legacy stale PASS rows: **" + str(health["stale_green_rows"]) +
                      "**; unknown-date PASS rows: **" +
                      str(health["unknown_timestamp_green_rows"]) + "**.\n\n")
            snapshot = report["snapshot_integrity"]["revenue"]
            out.write("Revenue count difference (Lifecycle - Net VAT): **" +
                      str(snapshot.get("invoice_count_delta_lifecycle_minus_net")) +
                      "**; timestamp ordering: **" +
                      snapshot.get("snapshot_order", "UNVERIFIED") +
                      "**. Verify original invoice IDs before any recalculation.\n\n")
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
