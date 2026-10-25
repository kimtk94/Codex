#!/usr/bin/env python3
"""Append newly discovered NBA Pool IDs to persistent checkbox ledger.

Safe for repeated CI runs: never alters existing decisions or their row positions.
Runs after an upstream ETL refreshes 'NBA Action Pool' (if any).
"""
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account
from bi_mail_review_sync import auth
from nba_register_new_ids import record_key

BOOK = os.getenv("NBA_SHEET_ID", "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
POOL = "NBA Action Pool"
CHECK = "NBA Decision Checkboxes"


def rows(s, name, range_):
    return s.values().get(
        spreadsheetId=BOOK, range=f"'{name}'!{range_}",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute().get("values", [])


def sync(api, dry_run=False):
    pool = rows(api, POOL, "D1:E20000")
    check = rows(api, CHECK, "A1:C20000")
    if not pool or pool[0][:2] != ["Source", "Record ID"]:
        raise ValueError("Unexpected NBA Pool header (D:E)")
    if not check or check[0][:2] != ["Source", "Record ID"]:
        raise ValueError("Unexpected NBA Decision Checkboxes header")
    existing = set()
    for r in check[1:]:
        if len(r) < 2 or not str(r[0]).strip() or not str(r[1]).strip():
            continue
        k = record_key({"Source":r[0], "Record ID":r[1]})
        if k in existing:
            raise ValueError("Duplicate checkbox key: " + str(k))
        existing.add(k)
    incoming, seen = [], set()
    for r in pool[1:]:
        if len(r) < 2 or not str(r[0]).strip() or not str(r[1]).strip():
            continue
        k = record_key({"Source":r[0], "Record ID":r[1]})
        if k in seen:
            raise ValueError("Duplicate pool key: " + str(k))
        seen.add(k)
        if k not in existing:
            incoming.append([str(r[0]), str(r[1]), False])
    if incoming and not dry_run:
        api.values().append(
            spreadsheetId=BOOK,
            range=f"'{CHECK}'!A:C",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values":incoming},
        ).execute()
    print(f"NBA_POOL={len(seen)} REGISTERED={len(existing)} NEW_IDS={len(incoming)} DRY_RUN={dry_run}")
    return len(incoming)


def main():
    api = auth()
    sync(api, dry_run=os.getenv("NBA_DRY_RUN", "false").lower() == "true")


if __name__ == "__main__":
    main()
