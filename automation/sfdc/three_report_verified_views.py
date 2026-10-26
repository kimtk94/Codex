#!/usr/bin/env python3
"""Generate read-only business-safe Salesforce relationship views from validated raw exports.

Writes ONLY the two explicitly generated tabs. No financial realization, manual decisions,
existing followup sheets, Salesforce, or source report data are modified.
"""
import collections
import datetime as dt
import json
import os
import sys
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from three_report_email_ingest import SHEET, KST, SCHEMAS, AUDIT_TAB, request, a1, column_name
from three_report_relationship_qc import read_tab, make_index, field

VERIFIED = "SFDC Verified Relations"
REVIEW = "SFDC Quote Link Review"
VERIFIED_HEADER = [
    "Quotation ID", "Opportunity ID", "Opportunity Name", "Account Name",
    "Opportunity Stage", "Opportunity Owner", "Lead Converted ID", "Lead Match",
    "Lead Status", "Quote Active (report only)", "Quote Process Rows",
    "Quote Product IDs", "Quote Total USD (unverified)", "Relation State", "Checked KST"
]
REVIEW_HEADER = [
    "Quotation ID", "Quote Process Rows", "Distinct Opportunity IDs",
    "Opportunity ID Missing Rows", "Opportunity IDs Not In Export",
    "Reason", "Review State", "Checked KST"
]

def build(leads, opportunities, quotations, timestamp):
    li, oi, qi = (make_index(x[0]) for x in (leads, opportunities, quotations))
    lead_by_id = {field(r, li, "SFDC Lead ID"): r for r in leads[1:]
                  if field(r, li, "SFDC Lead ID")}
    opp_by_id = {field(r, oi, "Opportunity ID"): r for r in opportunities[1:]
                 if field(r, oi, "Opportunity ID")}
    groups = collections.defaultdict(list)
    for row in quotations[1:]:
        qid = field(row, qi, "SFDC Quotation ID")
        if qid:
            groups[qid].append(row)
    verified, review = [VERIFIED_HEADER], [REVIEW_HEADER]
    for qid, rows in sorted(groups.items()):
        opp_ids = {field(r, qi, "Opportunity ID") for r in rows if field(r, qi, "Opportunity ID")}
        missing = sum(not field(r, qi, "Opportunity ID") for r in rows)
        unknown = sorted(x for x in opp_ids if x not in opp_by_id)
        reasons = []
        if missing:
            reasons.append("MISSING_OPPORTUNITY_ID")
        if unknown:
            reasons.append("OPPORTUNITY_NOT_IN_EXPORT")
        if len(opp_ids) != 1:
            reasons.append("MULTIPLE_OR_ZERO_OPPORTUNITY_IDS")
        if reasons:
            review.append([qid, len(rows), len(opp_ids), missing, len(unknown),
                           " | ".join(reasons), "NEEDS_REVIEW", timestamp])
            continue
        oppid = next(iter(opp_ids))
        opp = opp_by_id[oppid]
        leadid = field(opp, oi, "Lead Converted ID")
        lead = lead_by_id.get(leadid)
        actives = {field(r, qi, "Active").strip().upper() for r in rows if field(r, qi, "Active")}
        active = next(iter(actives)) if len(actives) == 1 else "MIXED_OR_UNKNOWN"
        product_ids = {field(r, qi, "Quotation Product ID") for r in rows if field(r, qi, "Quotation Product ID")}
        # Multiple process rows may repeat quote-level amount: display only a candidate,
        # never sum and never mark recognized revenue.
        amounts = {field(r, qi, "Total Price USD (converted)") for r in rows if field(r, qi, "Total Price USD (converted)")}
        amount = next(iter(amounts)) if len(amounts) == 1 else ""
        verified.append([
            qid, oppid, field(opp, oi, "Opportunity Name"), field(opp, oi, "Account Name"),
            field(opp, oi, "Stage"), field(opp, oi, "Opportunity Owner"), leadid,
            ("MATCHED" if lead else "OUTSIDE_CURRENT_LEAD_REPORT") if leadid else "NO_CONVERTED_LEAD",
            field(lead, li, "Lead Status") if lead else "",
            active, len(rows), len(product_ids), amount,
            "QUOTE_OPPORTUNITY_ID_VERIFIED_NOT_REVENUE", timestamp
        ])
    return verified, review

def replace_generated(session, tab, rows):
    meta = request(session, "GET", "?fields=sheets.properties(title,sheetId,gridProperties)")
    tabs = {x["properties"]["title"]: x["properties"] for x in meta.get("sheets", [])}
    target_rows, target_cols = max(len(rows), 100), max(len(rows[0]), 18)
    if tab not in tabs:
        request(session, "POST", ":batchUpdate", json={"requests": [
            {"addSheet": {"properties": {"title": tab,
                "gridProperties": {"rowCount": target_rows, "columnCount": target_cols,
                                   "frozenRowCount": 1}}}}]})
        old_rows, old_cols = 0, 0
    else:
        p = tabs[tab]
        old_rows = p.get("gridProperties", {}).get("rowCount", 0)
        old_cols = p.get("gridProperties", {}).get("columnCount", 0)
        if old_rows < target_rows or old_cols < target_cols:
            request(session, "POST", ":batchUpdate", json={"requests": [
                {"updateSheetProperties": {"properties": {
                    "sheetId": p["sheetId"], "gridProperties": {
                        "rowCount": max(old_rows, target_rows),
                        "columnCount": max(old_cols, target_cols)}},
                 "fields": "gridProperties.rowCount,gridProperties.columnCount"}}]})
    end_rows, end_cols = max(old_rows, target_rows), max(old_cols, target_cols)
    replacement = [r + [""] * (end_cols - len(r)) for r in rows]
    replacement.extend([[""] * end_cols for _ in range(end_rows - len(replacement))])
    request(session, "POST", "/values:batchUpdate", json={
        "valueInputOption": "RAW", "data": [{"range": "'" + tab + "'!A1:" +
            column_name(end_cols) + str(end_rows), "values": replacement}]})

def main():
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    session = AuthorizedSession(credentials)
    meta = request(session, "GET", "?fields=sheets.properties.title")
    tabs = {x["properties"]["title"] for x in meta.get("sheets", [])}
    missing = [k for k, cfg in SCHEMAS.items() if cfg["tab"] not in tabs]
    if missing:
        print("SFDC_RELATIONS_PROMOTION_BLOCKED_MISSING=" + ",".join(missing))
        return
    audit = read_tab(session, AUDIT_TAB) if AUDIT_TAB in tabs else []
    states = {r[0]: r[8] for r in audit[1:] if len(r) > 8}
    if any(states.get(k) not in ("STAGED_NOT_PROMOTED", "PRESERVED_NO_NEW_REPORT") for k in SCHEMAS):
        print("SFDC_RELATIONS_PROMOTION_BLOCKED_SOURCE_QC")
        return
    sources = {kind: read_tab(session, cfg["tab"]) for kind, cfg in SCHEMAS.items()}
    stamp = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    verified, review = build(sources["Leads"], sources["Opportunities"], sources["Quotation"], stamp)
    print("SFDC_RELATIONS_BUILD=" + json.dumps({
        "verified_quotes": len(verified) - 1,
        "review_quote_ids": len(review) - 1,
        "source_leads": len(sources["Leads"]) - 1,
        "source_opportunities": len(sources["Opportunities"]) - 1,
        "source_quote_process_rows": len(sources["Quotation"]) - 1
    }, sort_keys=True))
    if os.getenv("SFDC_RELATIONS_APPLY", "false").lower() != "true":
        print("SFDC_RELATIONS_DRY_RUN=true")
        return
    replace_generated(session, VERIFIED, verified)
    replace_generated(session, REVIEW, review)
    print("SFDC_RELATIONS_GENERATED_TABS_UPDATED=true")

if __name__ == "__main__":
    main()
