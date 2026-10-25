#!/usr/bin/env python3
"""Refresh NBA Action Pool from existing Google Sheets sources, preserving decisions.

No changes to NBA Decision Checkboxes. Does not send mail or modify SFDC.
Stops safely before writing if candidate count exceeds pool grid capacity.
"""
import os
from datetime import date
from googleapiclient.discovery import build
from bi_mail_review_sync import auth
from today_action_v2 import mail_rows
from today_action_top10 import css_rows, lead_rows

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
    values = css_rows(css, today) + lead_rows(leads, today) + mail_rows(mail)
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
    leads = fetch(api, BOOK, "Lead Email Followup", "AD700")
    mail = fetch(api, MAIL_BOOK, "BI Unanswered Triage", "U1200")
    rows = build_candidates(css, leads, mail, today)
    metadata = api.get(spreadsheetId=BOOK, fields="sheets(properties(title,gridProperties(rowCount)))").execute()
    grid = next((x["properties"]["gridProperties"]["rowCount"] for x in metadata["sheets"]
                 if x["properties"]["title"] == "NBA Action Pool"), 0)
    if not rows or len(rows) + 1 > grid:
        raise ValueError(f"Unsafe candidate count={len(rows)} exceeds pool capacity={grid}")
    if dry_run:
        print(f"NBA_POOL_DRY_RUN={len(rows)} GRID={grid}")
        return len(rows)
    # Never touch O:P (completion and rank formulas), nor checkbox ledger.
    api.values().clear(spreadsheetId=BOOK, range="'NBA Action Pool'!A2:N"+str(grid), body={}).execute()
    chunk = 250
    for offset in range(0, len(rows), chunk):
        start = offset + 2
        values = rows[offset:offset+chunk]
        api.values().update(spreadsheetId=BOOK,
                            range=f"'NBA Action Pool'!A{start}:N{start+len(values)-1}",
                            valueInputOption="RAW", body={"values":values}).execute()
    print(f"NBA_POOL_UPDATED={len(rows)} DECISIONS_UNCHANGED=true")
    return len(rows)


def main():
    sync(auth(), dry_run=os.getenv("NBA_DRY_RUN", "true").lower() != "false")


if __name__ == "__main__":
    main()
