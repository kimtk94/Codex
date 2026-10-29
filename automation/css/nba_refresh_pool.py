#!/usr/bin/env python3
"""Refresh NBA Action Pool from existing Google Sheets sources, preserving decisions.

No changes to NBA Decision Checkboxes. Does not send mail or modify SFDC.
Stops safely before writing if candidate count exceeds pool grid capacity.
"""
import os
from datetime import date, datetime, timedelta, timezone
from googleapiclient.discovery import build
from nba_google_auth import auth
from today_action_v2 import mail_rows
from today_action_top10 import css_rows
from personal_lead_priority import personal_lead_rows

BOOK = os.getenv("NBA_SHEET_ID", "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
MAIL_BOOK = os.getenv("CSS_SHEET_ID", "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
FIELDS = ["Rank", "Priority", "Score", "Source", "Record ID", "Institution",
          "Customer", "Project ID", "Issue", "Next Action", "Due/Event Date",
          "Verification", "Source Tab", "Snapshot Date"]


def fetch(api, book, tab, bound):
    result = api.values().get(spreadsheetId=book, range=f"'{tab}'!A1:{bound}",
                              valueRenderOption="FORMATTED_VALUE").execute()
    matrix = result.get("values", [])
    if not matrix:
        raise ValueError(f"Source tab empty: {tab}")
    names = matrix[0]
    return [dict(zip(names, (row + [""] * len(names))[:len(names)])) for row in matrix[1:]]


def build_candidates(css, leads, mail, today):
    values = css_rows(css, today) + personal_lead_rows(leads, today) + mail_rows(mail)
    unique = {}
    for row in values:
        source, record_id = str(row.get("Source", "")).strip(), str(row.get("Record ID", "")).strip()
        if not source or not record_id:
            continue
        identity = (source.upper(), record_id.upper())
        if identity not in unique or int(row["Score"]) > int(unique[identity]["Score"]):
            unique[identity] = row
    ranked = sorted(unique.values(), key=lambda r: (-int(r["Score"]), r["Source"], r["Record ID"]))
    result = []
    for idx, item in enumerate(ranked, 1):
        result.append([idx, item.get("Priority", ""), int(item.get("Score", 0)),
            item["Source"], item["Record ID"], item.get("Institution", ""),
            item.get("Customer", ""), item.get("Project ID", ""), item.get("Issue", ""),
            item.get("Action", ""), item.get("Due Date", ""), item.get("Verification", ""),
            item.get("Source Tab", ""), today.isoformat()])
    return result


def sync(api, dry_run=True):
    today = date.today()
    css = fetch(api, BOOK, "BI Followup Unified", "W500")
    leads = fetch(api, BOOK, "Lead My Sent Audit", "T650")
    sf = fetch(api, BOOK, "SFDC Email Leads Raw", "W700")
    mail = fetch(api, MAIL_BOOK, "BI Unanswered Triage", "U1200")
    # Fail closed if the personal audit is stale or does not cover the latest
    # report: avoid publishing false "never contacted" first-email tasks.
    audited = {str(r.get("Lead ID", "")).strip().upper() for r in leads}
    latest = {str(r.get("SFDC Lead ID", "")).strip().upper()
              for r in sf if str(r.get("SFDC Lead ID", "")).strip()}
    if not latest or audited != latest:
        raise ValueError("Personal sent audit IDs do not match latest SFDC Lead Report")
    # Health is a label/value ledger rather than a conventional table.
    state_matrix = api.values().get(spreadsheetId=BOOK,
        range="'Automation Health'!A1:D40", valueRenderOption="FORMATTED_VALUE"
        ).execute().get("values", [])
    status = next((r for r in state_matrix if r and r[0] == "Lead My Sent Audit"), None)
    if not status or len(status)<3 or status[2]!="PASS_VERIFIED":
        raise ValueError("Personal sent audit health is not verified")
    time_values = [str(r.get("Latest QQ Outbound Checked","")).strip() for r in leads]
    if not time_values or any(t!=time_values[0] for t in time_values):
        raise ValueError("Personal QQ freshness timestamp missing or inconsistent")
    try:
        last_qq = datetime.fromisoformat(time_values[0].replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("Personal QQ freshness timestamp malformed") from exc
    if last_qq.tzinfo is None or abs((datetime.now(timezone.utc)-last_qq).total_seconds())>72*3600:
        raise ValueError("Personal QQ outbound audit stale")
    rows = build_candidates(css, leads, mail, today)
    # Protect durable decisions: NEVER requeue a checked or explicitly
    # excluded record on the next pool refresh.
    checkbox_matrix = api.values().get(spreadsheetId=BOOK,
        range="'NBA Decision Checkboxes'!A1:C4000",
        valueRenderOption="UNFORMATTED_VALUE").execute().get("values", [])
    if not checkbox_matrix or checkbox_matrix[0][:2] != ["Source","Record ID"]:
        raise ValueError("Persistent decision checkbox ledger unavailable")
    completed = {(str(x[0]).strip().upper(),str(x[1]).strip().upper())
                 for x in checkbox_matrix[1:] if len(x)>2 and
                 str(x[2]).strip().upper() in {"TRUE","1","DONE","YES"}}
    decision_rows = fetch(api, BOOK, "Lead Decision Ledger", "G700")
    blocked = {"DONE","CLOSED","EXCLUDED","SKIP","RESOLVED"}
    excluded = {("LEAD",str(x.get("Lead ID","")).strip().upper())
                for x in decision_rows
                if str(x.get("Decision","")).strip().upper() in blocked}
    rows = [x for x in rows if (str(x[3]).upper(),str(x[4]).upper())
            not in completed|excluded]
    contacted = {str(r.get("Lead ID", "")).strip().upper() for r in leads
                 if str(r.get("My Mail Status", "")).strip().upper()
                 == "SENT_AFTER_LEAD_CONFIRMED"}
    leaks = [r[4] for r in rows if r[3] == "LEAD" and str(r[4]).upper() in contacted]
    if leaks:
        raise ValueError("Confirmed-sent Leads leaked into NBA candidates: " + ",".join(leaks[:10]))
    # Re-rank after excluded/checked records have been removed.
    for index, item in enumerate(rows, 1):
        item[0] = index
    metadata = api.get(spreadsheetId=BOOK, fields="sheets(properties(title,gridProperties(rowCount)))").execute()
    grid = next((x["properties"]["gridProperties"]["rowCount"] for x in metadata["sheets"]
                 if x["properties"]["title"] == "NBA Action Pool"), 0)
    if not rows or len(rows) + 1 > grid:
        raise ValueError(f"Unsafe candidate count={len(rows)} exceeds pool capacity={grid}")
    if dry_run:
        print(f"NBA_POOL_DRY_RUN={len(rows)} GRID={grid}")
        return len(rows)
    # One values batch update: never clear the active pool before its replacement is ready.
    # Blank stale A:N tail in the same request; leave O:P and checkbox ledger untouched.
    replacement = rows + [[""] * len(FIELDS) for _ in range(grid - 1 - len(rows))]
    api.values().batchUpdate(
        spreadsheetId=BOOK,
        body={"valueInputOption":"RAW","data":[{
            "range":f"'NBA Action Pool'!A2:N{grid}",
            "values":replacement,
        }]},
    ).execute()
    print(f"NBA_POOL_UPDATED={len(rows)} DECISIONS_UNCHANGED=true")
    return len(rows)


def main():
    sync(auth(), dry_run=os.getenv("NBA_DRY_RUN", "true").lower() != "false")


if __name__ == "__main__":
    main()
