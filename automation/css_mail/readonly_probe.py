#!/usr/bin/env python3
"""QQ Mail IMAP read-only health probe; logs aggregate counts only."""
import datetime as dt
import email.utils
import imaplib
import json
import os
import sys

KST = dt.timezone(dt.timedelta(hours=9))
IMAP_HOST = "imap.qq.com"
IMAP_PORT = 993

def required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError("Missing required QQ Mail environment configuration")
    return value

def search_count(imap, *criteria):
    status, data = imap.uid("SEARCH", None, *criteria)
    if status != "OK":
        raise RuntimeError("IMAP search failed")
    return len(data[0].split()) if data and data[0] else 0

def run():
    user = required("CSS_QQ_MAIL_ADDRESS")
    auth_code = required("CSS_QQ_MAIL_AUTH_CODE")
    hours = int(os.getenv("CSS_MAIL_LOOKBACK_HOURS", "48"))
    if not 1 <= hours <= 168:
        raise RuntimeError("Invalid lookback window")
    # IMAP SINCE is date-granular. UTC date boundary is intentionally a superset
    # of the rolling-hours interval; this report is a health indicator, not
    # an exact hourly volume measurement.
    boundary = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).date()
    since = boundary.strftime("%d-%b-%Y")
    mailbox_counts = {}
    stage = "connect"
    print("CSS_QQ_IMAP_STAGE: connect", flush=True)
    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=30) as imap:
        print("CSS_QQ_IMAP_STAGE: connected", flush=True)
        print("CSS_QQ_IMAP_STAGE: authenticate", flush=True)
        status, _ = imap.login(user, auth_code)
        print("CSS_QQ_IMAP_STAGE: authenticated", flush=True)
        if status != "OK":
            raise RuntimeError("QQ IMAP login failed")
        for label, candidates in {
            "inbox": ["INBOX"],
            # QQ Mail may use localized or provider-specific Sent folder names.
            "sent": ["Sent Messages", "Sent", "Sent Items"],
        }.items():
            print("CSS_QQ_IMAP_STAGE: select_" + label, flush=True)
            found = False
            for name in candidates:
                status, _ = imap.select('"' + name + '"', readonly=True)
                if status == "OK":
                    print("CSS_QQ_IMAP_STAGE: search_" + label, flush=True)
                    mailbox_counts[label] = {"recent_since_utc_date": search_count(imap, "SINCE", since)}
                    if label == "inbox":
                        mailbox_counts[label]["unread_recent_since_utc_date"] = search_count(imap, "UNSEEN", "SINCE", since)
                    found = True
                    break
            if not found:
                mailbox_counts[label] = {"status": "FOLDER_NOT_FOUND"}
        print("CSS_QQ_IMAP_STAGE: logout", flush=True)
        imap.logout()
    output = {
        "status": "PASS",
        "provider": "QQ_MAIL",
        "mode": "READ_ONLY",
        "lookback_hours_requested": hours,
        "since_utc_date_inclusive": boundary.isoformat(),
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "metrics": mailbox_counts,
    }
    with open(os.getenv("CSS_MAIL_REPORT_PATH", "css_mail_probe.json"), "w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)
    print("CSS_QQ_IMAP_PROBE: PASS (sanitized aggregate metrics only)")

if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        # Deliberately suppress exception payload to prevent credential exposure.
        print("CSS_QQ_IMAP_PROBE: FAILED (" + type(error).__name__ + ")", file=sys.stderr)
        sys.exit(1)
