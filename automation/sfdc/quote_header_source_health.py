#!/usr/bin/env python3
"""Read-only validation of Salesforce subscribed Quote HEADER export freshness.

The 25-column process report is a different source and never refreshes this
header. All emitted evidence is aggregate; no customer, mail or quote fields.
No sheet, QQ mail, SFDC or Feishu write.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from urllib.parse import quote

BOOK = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
TAB = "SFDC Quote Export"
KST = dt.timezone(dt.timedelta(hours=9))
MAX_AGE_HOURS = 72
MIN_QUOTE_ROWS = 10
HEADER = "Exported At KST"


def parsed_date(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_QUOTE_HEADER_TIMESTAMP")
    stripped = value.strip()
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} KST", stripped):
        raise ValueError("INVALID_QUOTE_HEADER_TIMESTAMP")
    return dt.datetime.strptime(stripped[:-4], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)


def assess(values, now=None):
    now = now or dt.datetime.now(KST)
    if not isinstance(now, dt.datetime) or now.tzinfo is None:
        raise ValueError("AWARE_CLOCK_REQUIRED")
    if not values or values[0] != [HEADER]:
        raise ValueError("QUOTE_HEADER_COLUMN_MISMATCH")
    rows = [v for v in values[1:] if v and str(v[0]).strip()]
    if len(rows) < MIN_QUOTE_ROWS:
        return {"status": "HEADER_MISSING_OR_TOO_SMALL", "row_count": len(rows),
                "age_hours": None, "max_age_hours": MAX_AGE_HOURS,
                "original_sfdc_verified": False}
    stamps = {parsed_date(str(r[0])) for r in rows}
    if len(stamps) != 1:
        return {"status": "MIXED_EXPORT_TIMESTAMPS", "row_count": len(rows),
                "distinct_timestamps": len(stamps), "age_hours": None,
                "max_age_hours": MAX_AGE_HOURS, "original_sfdc_verified": False}
    timestamp = next(iter(stamps))
    age = (now.astimezone(KST) - timestamp).total_seconds() / 3600
    if age < -0.2:
        return {"status": "FUTURE_EXPORT_TIMESTAMP", "row_count": len(rows),
                "age_hours": round(age, 2), "max_age_hours": MAX_AGE_HOURS,
                "original_sfdc_verified": False}
    return {"status": "HEADER_MIRROR_RECENT" if age <= MAX_AGE_HOURS else "STALE_QUOTE_HEADER",
            "row_count": len(rows), "age_hours": round(age, 2),
            "exported_at_kst": timestamp.isoformat(),
            "max_age_hours": MAX_AGE_HOURS,
            "original_sfdc_verified": False}


def read_column():
    raw = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        raise RuntimeError("READONLY_CREDENTIAL_MISSING")
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    credential = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    client = AuthorizedSession(credential)
    a1 = quote("'" + TAB + "'!J1:J2500", safe="")
    url = "https://sheets.googleapis.com/v4/spreadsheets/" + BOOK + "/values/" + a1
    response = client.get(url, timeout=30)
    if not response.ok:
        raise RuntimeError("QUOTE_HEADER_SOURCE_READ_FAILED")
    return response.json().get("values", [])


def main():
    try:
        state = assess(read_column())
    except Exception as error:
        state = {"status": "SOURCE_UNAVAILABLE", "error_type": type(error).__name__,
                 "original_sfdc_verified": False}
    print(json.dumps(state, sort_keys=True, separators=(",", ":")))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as file:
            file.write("### Salesforce Quote header source integrity\n")
            file.write("Status: **" + state["status"] + "**; this excludes the separate process report.\n")
            file.write("Original SFDC freshness is never certified by this mirror alone.\n")
    if state["status"] != "HEADER_MIRROR_RECENT":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
