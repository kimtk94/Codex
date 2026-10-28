#!/usr/bin/env python3
"""Mail-only operations derived from canonical staging projection; does not duplicate SFDC.

This table is advisory. Header evidence cannot establish actual unanswered state
because threading headers and complete history are unavailable.
"""
import datetime as dt
import re
import sys
import urllib.parse
from collections import Counter
from email.utils import getaddresses

import incremental_sync as src
import canonical_mail_reader as canonical

TAB = "CSS Mail Operations"
HEAD = ["section","date_or_received_at","status","sender_or_direction",
        "subject_or_metric","value","reference","analysis_scope"]
READ_COLS = 18
MAX_ROWS = 100000

def clean_subject(s):
    s = str(s or "").strip()
    while True:
        updated = re.sub(r"^(?:(?:re|fw|fwd|답장|전달)\s*[:：]\s*)", "", s, flags=re.I).strip()
        if updated == s:
            break
        s = updated
    return re.sub(r"\s+", " ", s).casefold()

def address_set(s):
    return {addr.lower() for _,addr in getaddresses([str(s or "")]) if addr}

def parsedate(s):
    try:
        result = dt.datetime.fromisoformat(str(s))
        if not result.tzinfo: return None
        return result.astimezone(dt.timezone.utc)
    except (ValueError, TypeError):
        return None

def compute(data):
    if not data or data[0][:len(src.COLS)] != src.COLS:
        raise RuntimeError("Canonical staging projection schema mismatch")
    entries = []
    for cells in data[1:]:
        row = dict(zip(src.COLS, list(cells)+[""]*(len(src.COLS)-len(cells))))
        if row["direction"] not in ("INBOUND","OUTBOUND"): continue
        row["_time"] = parsedate(row["received_at"])
        row["_subject"] = clean_subject(row["subject"])
        entries.append(row)
    sent = [r for r in entries if r["direction"]=="OUTBOUND"]
    incoming = [r for r in entries if r["direction"]=="INBOUND"]
    days = Counter()
    for row in entries:
        if row["_time"]:
            date=row["_time"].astimezone(src.KST).strftime("%Y-%m-%d")
            days[(date,row["direction"])] += 1
    rows = []
    for date in sorted({date for date,_ in days},reverse=True)[:31]:
        rows.append(["DAILY_VOLUME",date,"HEADER_ONLY","INBOUND",
                     "received_count",days[(date,"INBOUND")],"","partial_collected_window"])
        rows.append(["DAILY_VOLUME",date,"HEADER_ONLY","OUTBOUND",
                     "sent_count",days[(date,"OUTBOUND")],"","partial_collected_window"])
    # This is a candidate list, never definitive 'unanswered': no In-Reply-To,
    # References, mailbox-wide history, or guarantee of customer-mail continuity.
    for r in sorted(incoming,key=lambda a:a["_time"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc),reverse=True):
        subject=r["_subject"]
        who=address_set(r["from_email"])
        if not subject or not who or not r["_time"]:
            continue
        matched=any(
            v["_subject"]==subject
            and v["_time"] and v["_time"]>=r["_time"]
            and (who & (address_set(v["recipient_to"])|address_set(v["cc"])))
            for v in sent
        )
        if not matched:
            rows.append(["REPLY_REVIEW",r["received_at"],"NEEDS_MANUAL_REVIEW",
                         r["from_email"][:200],r["subject"][:300],"",
                         r["ingest_key"],"header-only; incomplete history; not confirmed unanswered"])
        if len(rows)>=500: break
    return [HEAD]+rows

def q(range_name):
    return urllib.parse.quote("'"+TAB+"'!"+range_name,safe="")

def main():
    session=src.authorize()
    base=src.endpoint()
    source={"values":canonical.read_staging_compatible(session)}
    output=compute(source.get("values",[]))
    meta=src.api(session,"GET",base+"?fields=sheets.properties.title")
    titles={s["properties"]["title"] for s in meta.get("sheets",[])}
    if TAB not in titles:
        src.api(session,"POST",src.endpoint(":batchUpdate"),
                json={"requests":[{"addSheet":{"properties":{"title":TAB,"gridProperties":{"frozenRowCount":1}}}}]})
    # One managed tab only. Existing CSS and SFDC tabs remain untouched.
    dest=src.endpoint("/values/"+q("A1:H1000"))
    src.api(session,"POST",dest+":clear",json={})
    src.api(session,"PUT",src.endpoint("/values/"+q("A1"))+"?valueInputOption=RAW",
            json={"values":output})
    print("CSS_MAIL_OPERATIONS_PASS rows="+str(len(output)-1)+" mode=ADVISORY no_sfdc_mutation")
if __name__=="__main__":
    try: main()
    except Exception as e:
        print("CSS_MAIL_OPERATIONS_FAILED "+(str(e) if isinstance(e,RuntimeError) else type(e).__name__),file=sys.stderr)
        sys.exit(1)
