#!/usr/bin/env python3
"""Incremental Tencent Exmail -> private Google Sheet staging; metadata only.

Never sends mail, mutates IMAP folders, or logs customer data.
Existing CSS tabs remain untouched. Gmail is not used.
"""
import datetime as dt
import email
import email.header
import imaplib
import json
import os
import re
import sys
import urllib.parse
from email.parser import BytesParser
from email.policy import default

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

BOOK = os.environ.get("CSS_SHEET_ID", "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
TAB = "CSS Git Ingest"
COLS = ["ingest_key","message_id","imap_uid","folder","uidvalidity","received_at","from_email",
        "recipient_to","cc","subject","amea_numbers","h_project_numbers","sam_numbers","batch_numbers",
        "fetched_at_utc","direction"]
KST = dt.timezone(dt.timedelta(hours=9))

def api(s,method,url,**kw):
    res=s.request(method,url,timeout=45,**kw)
    if not res.ok:
        try: reason=res.json().get("error",{}).get("status","UNKNOWN")
        except ValueError: reason="UNKNOWN"
        raise RuntimeError("Sheets "+method+" HTTP="+str(res.status_code)+" "+reason)
    return res.json() if res.content else {}

def authorize():
    raw=os.environ.get("GCP_SERVICE_ACCOUNT_JSON","")
    if not raw: raise RuntimeError("Missing GCP_SERVICE_ACCOUNT_JSON in TaehoonServer")
    cred=service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return AuthorizedSession(cred)

def endpoint(suffix=""):
    return "https://sheets.googleapis.com/v4/spreadsheets/"+BOOK+suffix

def ensure_tab(s):
    meta=api(s,"GET",endpoint()+"?fields=sheets.properties.title")
    found={x["properties"]["title"] for x in meta.get("sheets",[])}
    if TAB not in found:
        api(s,"POST",endpoint(":batchUpdate"),json={"requests":[{"addSheet":{"properties":{
            "title":TAB,"gridProperties":{"frozenRowCount":1}}}}]})
    rng=urllib.parse.quote("'"+TAB+"'!A1:P1",safe="")
    rows=api(s,"GET",endpoint("/values/"+rng)).get("values",[])
    if not rows:
        api(s,"PUT",endpoint("/values/"+rng)+"?valueInputOption=RAW",
            json={"values":[COLS]})
    elif rows[0]!=COLS:
        raise RuntimeError("Staging header mismatch; aborting to protect existing data")

def existing_keys(s):
    # Scan just one narrow key column, not customer data; bounded to 100k rows.
    rng=urllib.parse.quote("'"+TAB+"'!A2:A100000",safe="")
    rows=api(s,"GET",endpoint("/values/"+rng)).get("values",[])
    return {r[0] for r in rows if r and r[0]}

def folder_names(im):
    status, rows = im.list()
    if status != "OK":
        raise RuntimeError("IMAP LIST failed")
    found = []
    for raw in rows or []:
        val = raw.decode("utf-8", "replace")
        match = re.search(r' (?:"([^"]+)"|([^ "]+))$', val)
        if match:
            found.append((match.group(1) or match.group(2), val.lower()))
    return found

def decode_address(raw):
    from email.utils import getaddresses
    return ", ".join(addr.lower() for _,addr in getaddresses([str(raw or "")]) if addr)[:1000]

def date_str(raw):
    try:
        value=email.utils.parsedate_to_datetime(str(raw))
        return value.isoformat() if value else ""
    except (ValueError,TypeError,IndexError):
        return ""

def pattern(p, value):
    return ", ".join(sorted(set(re.findall(p,value,re.I))))

def collect(im, folder, direction, seen, limit):
    status,_=im.select('"'+folder.replace('"','')+'"',readonly=True)
    if status!="OK": raise RuntimeError("IMAP folder select failed")
    status,uv=im.response("UIDVALIDITY")
    if not uv or not uv[0]: raise RuntimeError("UIDVALIDITY unavailable")
    uidvalidity=uv[0].decode("ascii","replace")
    days=int(os.environ.get("CSS_IMAP_SCAN_DAYS","3"))
    if days<1 or days>14: raise RuntimeError("Scan days out of bounds")
    date=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=days)).strftime("%d-%b-%Y")
    status,hit=im.uid("SEARCH",None,"SINCE",date)
    if status!="OK": raise RuntimeError("IMAP UID search failed")
    ids=(hit[0] or b"").split()
    # Limit per run without silently skipping oldest items: reject backlog and
    # require explicit resync plan rather than advancing checkpoint.
    if len(ids)>limit:
        raise RuntimeError("BACKLOG_LIMIT: widen batching after reviewing mailbox volume")
    output=[]
    for uid in ids:
        key=folder+"|"+uidvalidity+"|"+uid.decode("ascii")
        if key in seen: continue
        status,body=im.uid("FETCH",uid,"(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID DATE FROM TO CC SUBJECT)])")
        if status!="OK": raise RuntimeError("IMAP header fetch failed")
        payload=next((r[1] for r in body if isinstance(r,tuple) and isinstance(r[1],bytes)),None)
        if payload is None: raise RuntimeError("IMAP missing header data")
        msg=BytesParser(policy=default).parsebytes(payload,headersonly=True)
        subject=str(msg.get("Subject",""))[:500]
        now=dt.datetime.now(dt.timezone.utc).isoformat()
        row=[key,str(msg.get("Message-ID",""))[:300],uid.decode("ascii"),folder,uidvalidity,
             date_str(msg.get("Date")) ,decode_address(msg.get("From")),
             decode_address(msg.get("To")),decode_address(msg.get("Cc")),subject,
             pattern(r"AMEA\d{7,}",subject),pattern(r"\bH[- ]?\d{5,}\b",subject),
             pattern(r"\bSAM[- ]?\d{4,}\b",subject),pattern(r"\bBATCH[- ]?\d{4,}\b",subject),
             now,direction]
        output.append(row)
    return output

def main():
    # Check Sheets access BEFORE retrieving customer metadata.
    print("CSS_SYNC_STAGE: google_auth", flush=True)
    s=authorize()
    print("CSS_SYNC_STAGE: sheet_access", flush=True)
    ensure_tab(s)
    print("CSS_SYNC_STAGE: staging_ready", flush=True)
    seen=existing_keys(s)
    user=os.environ["CSS_QQ_MAIL_ADDRESS"]
    password=os.environ["CSS_QQ_MAIL_AUTH_CODE"]
    limit=int(os.environ.get("CSS_IMAP_MAX_FOLDER_SCAN","1500"))
    collected=[]
    print("CSS_SYNC_STAGE: qq_connect", flush=True)
    with imaplib.IMAP4_SSL("imap.exmail.qq.com",993,timeout=45) as im:
        im.login(user,password)
        print("CSS_SYNC_STAGE: qq_authenticated", flush=True)
        folders=folder_names(im)
        sent=next((f for f,t in folders if "\\sent" in t or f.lower() in
                   ("sent messages","sent","sent items")),None)
        if not sent:
            raise RuntimeError("Sent folder mapping missing; check IMAP LIST and Exmail special-use names")
        print("CSS_SYNC_STAGE: folders_resolved", flush=True)
        collected+=collect(im,"INBOX","INBOUND",seen,limit)
        collected+=collect(im,sent,"OUTBOUND",seen,limit)
        im.logout()
    # Read again to prevent replay after partial success. Concurrency is serialized
    # by GitHub Actions, and old data is never overwritten.
    print("CSS_SYNC_STAGE: headers_collected", flush=True)
    seen=existing_keys(s)
    new=[r for r in collected if r[0] not in seen]
    if new:
        rng=urllib.parse.quote("'"+TAB+"'!A:P",safe="")
        api(s,"POST",endpoint("/values/"+rng+":append")+"?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
            json={"values":new})
    print("CSS_SYNC_STAGE: sheet_write_complete", flush=True)
    print("CSS_MAIL_SYNC_PASS new="+str(len(new))+" existing_keys="+str(len(seen))+
          " fetched_headers="+str(len(collected))+" direction=both")
if __name__=="__main__":
    try: main()
    except Exception as e:
        print("CSS_MAIL_SYNC_FAILED "+str(e) if isinstance(e,RuntimeError) else
              "CSS_MAIL_SYNC_FAILED "+type(e).__name__,file=sys.stderr)
        sys.exit(1)
