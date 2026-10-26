#!/usr/bin/env python3
"""Read-only Opportunity template search from Google Sheets or a local CSV.

Never stores Google credentials in repo. No Salesforce API, no Save action.
"""
import argparse
import csv
import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path

SHEET_ID = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TAB = "SFDC Opportunity Template Catalog"
COLUMNS = ("Opportunity Owner", "Account Name", "Opportunity Name", "Stage",
           "Main Contact", "Main Contact CMS ID", "Amount Currency", "Amount",
           "Probability (%)", "Close Date", "Lead Source",
           "Opportunity Created Date", "Opportunity ID", "Lead Converted ID", "Account ID")

def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def load_sheet(sheet_id=SHEET_ID, tab=TAB):
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        import google.auth
    except ImportError as exc:
        raise RuntimeError("Install google-auth: py -3.12 -m pip install google-auth") from exc
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    key_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if key_path:
        credentials = service_account.Credentials.from_service_account_file(
            key_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    elif key_json:
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(key_json), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    else:
        try:
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        except google.auth.exceptions.DefaultCredentialsError as exc:
            raise RuntimeError("Google credentials not found. Use existing GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_SERVICE_ACCOUNT_JSON, or configure Application Default Credentials (ADC). Never commit a key.") from exc
    from urllib.parse import quote
    url = ("https://sheets.googleapis.com/v4/spreadsheets/" + sheet_id +
           "/values/" + quote("'" + tab.replace("'", "''") + "'!A1:O", safe="!':") )
    response = AuthorizedSession(credentials).get(url, timeout=40)
    response.raise_for_status()
    values = response.json().get("values", [])
    if not values:
        return []
    header = [clean(x) for x in values[0]]
    return [dict(zip(header, list(row) + [""] * max(0, len(header)-len(row))))
            for row in values[1:] if any(clean(x) for x in row)]

def dedupe(rows):
    result = {}
    for row in rows:
        key = clean(row.get("Opportunity ID"))
        if key and key not in result:
            result[key] = row
    return list(result.values())

def similarity(a, b):
    a, b = clean(a).casefold(), clean(b).casefold()
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()

def search(rows, account="", contact="", service="", top=10):
    scored = []
    for row in dedupe(rows):
        parts = (
            similarity(account, row.get("Account Name")) if account else 0,
            similarity(contact, row.get("Main Contact")) if contact else 0,
            similarity(service, row.get("Opportunity Name")) if service else 0)
        if max(parts) == 0:
            continue
        score = round(parts[0] * .5 + parts[1] * .3 + parts[2] * .2, 5)
        scored.append((score, row))
    scored.sort(key=lambda item: (-item[0], clean(item[1].get("Opportunity ID"))))
    return [{"score": score, "opportunity_id": row.get("Opportunity ID"),
             "account": row.get("Account Name"), "account_id": row.get("Account ID"),
             "contact": row.get("Main Contact"), "contact_cms_id": row.get("Main Contact CMS ID"),
             "opportunity_name": row.get("Opportunity Name"),
             "historical_stage": row.get("Stage"), "historical_currency": row.get("Amount Currency")}
            for score, row in scored[:top]]

def make_draft(match):
    return {"Account Name": match["account"], "Main Contact": match["contact"],
            "Account ID (reference only)": match["account_id"],
            "Contact CMS ID (reference only)": match["contact_cms_id"],
            "Service Line": "", "Opportunity Name": "", "Amount": "",
            "Close Date": "", "Stage": "", "Forecast Category": "", "Status": "",
            "Progress Description": "", "source_opportunity_id": match["opportunity_id"],
            "review_required": True, "salesforce_save_performed": False}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", help="Optional offline CSV; otherwise read Google Sheets")
    p.add_argument("--account", default="")
    p.add_argument("--contact", default="")
    p.add_argument("--service", default="")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--output", default="")
    args = p.parse_args()
    if not any([args.account, args.contact, args.service]):
        p.error("Specify --account, --contact or --service")
    if args.top < 1 or args.top > 50:
        p.error("--top must be between 1 and 50")
    rows = load_csv(args.csv) if args.csv else load_sheet()
    matches = search(rows, args.account, args.contact, args.service, args.top)
    report = {"source_rows": len(rows), "unique_opportunities": len(dedupe(rows)),
              "matches": matches, "draft": make_draft(matches[0]) if matches else None,
              "sfdc_write_performed": False}
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Saved:", output)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
if __name__ == "__main__":
    main()
