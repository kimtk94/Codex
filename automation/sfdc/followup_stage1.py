#!/usr/bin/env python3
"""API-free Salesforce follow-up consolidation from an existing private Google Sheet.

No Salesforce authentication, writes, or private-data logging.
Requires google-auth and requests, and service-account access to both Sheets.
"""
import csv
import datetime as dt
import json
import os
import re
import sys
from collections import defaultdict

import google.auth
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

SOURCE_ID = os.environ.get("SFDC_SOURCE_SHEET_ID", "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
OUTPUT_ID = os.environ.get("SFDC_OUTPUT_SHEET_ID", "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TABLES = {
    "leads": "Salesforce Lead Tracker",
    "enquiries": "Salesforce Enquiry Queue",
    "engagements": "Salesforce Engagements",
}
HEADER = ["priority_score","priority","source","record_id","object_type","institution","customer_name","email","service","latest_event","age_days","followup_status","recommended_action","record_link","source_uid","checked_at"]
KST = dt.timezone(dt.timedelta(hours=9))


def auth():
    value = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "").strip()
    if not value:
        raise RuntimeError("GCP_SERVICE_ACCOUNT_JSON secret missing")
    creds = service_account.Credentials.from_service_account_info(json.loads(value), scopes=SCOPES)
    return AuthorizedSession(creds)


def call(session, method, url, **kwargs):
    r = session.request(method, url, timeout=90, **kwargs)
    r.raise_for_status()
    return r.json() if r.content else {}


def read_table(session, sheet):
    import urllib.parse
    rng = urllib.parse.quote(f"'{sheet}'!A1:AG3000", safe="")
    data = call(session, "GET", f"https://sheets.googleapis.com/v4/spreadsheets/{SOURCE_ID}/values/{rng}")
    rows = data.get("values", [])
    if not rows:
        return []
    headings = [str(x).strip() for x in rows[0]]
    return [dict(zip(headings, list(r) + [""] * (len(headings) - len(r)))) for r in rows[1:] if any(str(x).strip() for x in r)]


def date_value(s):
    s = str(s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s[:19], fmt).replace(tzinfo=KST)
        except ValueError:
            pass
    return None


def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def build(tables):
    now = dt.datetime.now(KST)
    entries = {}
    def add(item):
        rid = clean(item["record_id"])
        key = rid if rid else ("unmatched:" + clean(item.get("source_uid")))
        if key == "unmatched:":
            return
        existing = entries.get(key)
        if existing:
            for col in ("institution","customer_name","email","service","record_link","source_uid"):
                if not existing.get(col) and item.get(col):
                    existing[col] = item[col]
            if item.get("latest_event") and (not existing.get("latest_event") or item["latest_event"] > existing["latest_event"]):
                existing["latest_event"] = item["latest_event"]
            existing["sources"].add(item["source"])
            existing["needs_followup"] |= item["needs_followup"]
        else:
            item["sources"] = {item["source"]}
            entries[key] = item

    for r in tables["leads"]:
        if clean(r.get("skip")).lower() in ("true","yes","1"):
            continue
        needs = clean(r.get("needs_action")).lower() in ("yes","true","1")
        add(dict(source="Lead Tracker", record_id=clean(r.get("record_id")), object_type=clean(r.get("object_type")),
                 institution=clean(r.get("institution")), customer_name=clean(r.get("customer_name")),
                 email=clean(r.get("customer_email")), service=clean(r.get("service_category")),
                 latest_event=clean(r.get("latest_event_at") or r.get("assigned_at")),
                 followup_status=clean(r.get("current_status")), record_link="",
                 source_uid="", needs_followup=needs))
    for r in tables["enquiries"]:
        sent = clean(r.get("mail_sent_after_enquiry")).lower()
        needs = sent not in ("yes","true")
        add(dict(source="Enquiry Queue", record_id=clean(r.get("record_id")), object_type=clean(r.get("object_type")),
                 institution=clean(r.get("institution")), customer_name=clean(r.get("customer_name")),
                 email=clean(r.get("customer_email")), service=clean(r.get("service_category")),
                 latest_event=clean(r.get("received_at")), followup_status=clean(r.get("email_followup_status")),
                 record_link=clean(r.get("record_link")), source_uid=clean(r.get("uid")), needs_followup=needs))
    # Engagement evidence only; never infer that an email has been sent.
    for r in tables["engagements"]:
        rid = clean(r.get("record_id"))
        if rid in entries:
            entries[rid]["sources"].add("Engagements")

    result = []
    for item in entries.values():
        event = date_value(item["latest_event"])
        age = max(0, (now - event).days) if event else None
        if not item["needs_followup"]:
            continue
        score = 50 + (min(age, 30) if age is not None else 0)
        if "Enquiry Queue" in item["sources"]:
            score += 15
        if not item["email"]:
            score -= 8
        score = min(100, max(0,score))
        priority = "긴급" if score >= 85 else "높음" if score >= 70 else "보통"
        action = "신규 문의 내용 확인 및 고객 연락 여부 검증" if "Enquiry Queue" in item["sources"] else "배정 Lead의 첫 연락/후속 메일 여부 확인"
        if not item["email"]:
            action += " (이메일 미확인)"
        result.append([score,priority,"; ".join(sorted(item["sources"])),item["record_id"],item["object_type"],
                       item["institution"],item["customer_name"],item["email"],item["service"],item["latest_event"],
                       age if age is not None else "",item["followup_status"],action,item["record_link"],
                       item["source_uid"],now.strftime("%Y-%m-%d %H:%M:%S %z")])
    return sorted(result, key=lambda r:(-r[0],str(r[3])))


def write_output(session, rows):
    # Dedicated output spreadsheet only. Sheet1 is the default tab of a newly created workbook.
    meta = call(session,"GET",f"https://sheets.googleapis.com/v4/spreadsheets/{OUTPUT_ID}?fields=sheets.properties")
    sheet = meta["sheets"][0]["properties"]["title"]
    import urllib.parse
    prefix = f"https://sheets.googleapis.com/v4/spreadsheets/{OUTPUT_ID}/values/"
    target = urllib.parse.quote(f"'{sheet}'!A1:P",safe="")
    call(session,"POST",prefix+target+":clear",json={})
    target = urllib.parse.quote(f"'{sheet}'!A1",safe="")
    call(session,"PUT",prefix+target+"?valueInputOption=RAW",json={"range":f"'{sheet}'!A1","majorDimension":"ROWS","values":[HEADER]+rows})


def main():
    session = auth()
    tables = {key:read_table(session, name) for key,name in TABLES.items()}
    rows = build(tables)
    write_output(session,rows)
    print(json.dumps({"status":"ok","lead_rows":len(tables["leads"]),"enquiry_rows":len(tables["enquiries"]),
                      "engagement_rows":len(tables["engagements"]),"followup_rows":len(rows)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"SFDC stage1 failed: {type(e).__name__}",file=sys.stderr)
        sys.exit(1)
