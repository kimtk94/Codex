#!/usr/bin/env python3
"""Read-only local customer identity search from the preverified Feishu Quote index.

No CRM writes, no remote requests, no mutation of source SQLite. Every result
is labelled with its institution; empty/inconsistent names never enter choices.
"""
import datetime as dt
import json
import re
import sqlite3
import sys
from pathlib import Path

DB=Path.home()/".sfdc_desktop"/"sfdc_feishu_quote_preclassified_PRIVATE.sqlite3"
ACCOUNT=re.compile(r"^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")
CONTACT=re.compile(r"^003[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$")

def read_identity_index(query,limit=25,now=None,db=None,account_id=""):
    if not isinstance(query,str) or (not query.strip() and not account_id) or len(query)>80 or (
        not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=25
    ):
        raise ValueError("IDENTITY_QUERY_INVALID")
    if not isinstance(account_id,str) or (account_id and not ACCOUNT.fullmatch(account_id)):
        raise ValueError("ACCOUNT_FILTER_INVALID")
    path=db or DB
    if not path.is_file():
        raise ValueError("IDENTITY_INDEX_NOT_AVAILABLE")
    now=now or dt.datetime.now(dt.timezone.utc)
    # A mode=ro connection cannot change the private source index.
    cx=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=5)
    try:
        meta=dict(cx.execute("SELECT k,v FROM meta").fetchall())
        expected=int(meta["quote_count"])
        actual=cx.execute("SELECT COUNT(*) FROM quote_reference").fetchone()[0]
        if expected<1 or expected!=actual:
            raise ValueError("IDENTITY_INDEX_COVERAGE_MISMATCH")
        indexed=dt.datetime.fromisoformat(meta["index_refreshed_utc"])
        if indexed.tzinfo is None:
            raise ValueError("IDENTITY_INDEX_TIME_UNVERIFIED")
        age=(now-indexed.astimezone(dt.timezone.utc)).total_seconds()
        state="FRESH" if -600<=age<=72*3600 else "STALE"
        term=query.strip().replace("\\","\\\\").replace("%","\\%").replace("_","\\_")
        pattern="%"+term+"%"
        records=cx.execute(
            """SELECT qid,quote_record_id,account_id,account_name,contact_id,contact_external_id,
                      contact_name,contact_email
               FROM quote_reference
               WHERE (account_name LIKE ? ESCAPE '\\'
                      OR contact_name LIKE ? ESCAPE '\\'
                      OR contact_email LIKE ? ESCAPE '\\')
                 AND TRIM(account_name)!='' AND TRIM(contact_name)!=''
                 AND (?='' OR account_id=?)
               ORDER BY CASE WHEN quote_record_id LIKE 'a0P%' THEN 0 ELSE 1 END,
                        qid DESC LIMIT 450""",
            (pattern,pattern,pattern,account_id,account_id)).fetchall()
    finally:
        cx.close()
    out=[];distinct=set()
    for qid,quote_id,aid,an,cid,external,cn,email in records:
        key=(aid or "",an or "",cid or "",external or "",cn or "",email or "")
        if key in distinct:continue
        distinct.add(key)
        out.append({
            "source_qid":qid,"source_quote_id":quote_id if re.fullmatch(r"a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?",quote_id or "") else "",
            "account_id":aid or "","account_name":an,
            "contact_id":cid or "","contact_external_id":external or "",
            "contact_name":cn,"contact_email":email or "",
            "crm_account_verified":bool(ACCOUNT.fullmatch(aid or "")),
            "crm_contact_verified":bool(CONTACT.fullmatch(cid or ""))
        })
        if len(out)>=limit:break
    return {
        "status":"PASS","rows":out,"source":"PRIVATE_FEISHU_QUOTE_REFERENCE_INDEX",
        "freshness":state,"indexed_at_utc":indexed.isoformat(),
        "account_filter":account_id,
        "quote_count":expected,"salesforce_write":False,"local_only":True
    }

def main():
    request=json.loads(sys.stdin.read(420))
    if (not isinstance(request,dict) or set(request)-{"query","limit","accountId"} or
        not {"query","limit"}.issubset(request)):
        raise ValueError("IDENTITY_FIELDS_INVALID")
    payload=read_identity_index(request["query"],request["limit"],account_id=request.get("accountId",""))
    print(json.dumps(payload,ensure_ascii=False,separators=(",",":")))

if __name__=="__main__":
    try:main()
    except ValueError as exc:
        text=str(exc)
        if not re.fullmatch(r"[A-Z0-9_]{3,70}",text):
            text="IDENTITY_SOURCE_FAILED"
        print(json.dumps({"status":"BLOCK","code":text,"salesforce_write":False}))
        sys.exit(1)
    except (OSError,KeyError,sqlite3.DatabaseError,TypeError):
        print('{"status":"BLOCK","code":"IDENTITY_SOURCE_UNAVAILABLE","salesforce_write":false}')
        sys.exit(1)
