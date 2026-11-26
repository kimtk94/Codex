#!/usr/bin/env python3
"""Bounded metadata-derived Statement source reads and original notice worklist.

This module is read-only; no source values, subjects, UIDs or private IDs
are emitted to logs. Exact J+X remains the installment identity.
"""
import datetime as dt
import re
import urllib.parse
from collections import Counter

KEY = re.compile(r"(?<![A-Z0-9_-])(J\d{3})-(X\d+SC\d+-Z\d+)(?![A-Z0-9_-])",re.I)
ISSUE = re.compile(r"^\s*❗?\ufe0f?\s*Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b",re.I)
REPLY = re.compile(r"^\s*(?:re|fw|fwd|회신|답장|전달)\s*[:：]",re.I)
VALID = {"FILENAME_PARSED","VERIFIED_LEGACY_FILENAME","EXISTS_IN_LEGACY"}
LIMITS = {"CSS Git Ingest":100000,"CSS Tax Invoice Extract":10000,"CSS Statement Amount Extract":5000}


def fail(code):
    raise RuntimeError("STATEMENT_SOURCE_"+code)


def cell(row,i):
    return str(row[i]) if i<len(row) and row[i] is not None else ""


def instant(raw):
    try:
        t=dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
        return t.astimezone(dt.timezone.utc) if t.tzinfo is not None else None
    except (ValueError,TypeError,AttributeError):
        return None


def exact_key(subject):
    keys={j.upper()+"-"+x.upper() for j,x in KEY.findall(subject)}
    return next(iter(keys)) if len(keys)==1 else ""


def ready(subject):
    low=subject.lower()
    return "statement" in low and ("ready for confirmation" in low or "revised statement" in low)


def read_full_source(session,book,tab,header,request=None):
    if tab not in LIMITS or not 1<=len(header)<=26:
        fail("READ_SCOPE")
    if request is None:
        from unified_followup_sync import req
        request=req
    root="https://sheets.googleapis.com/v4/spreadsheets/"+book
    def meta():
        obj=request(session,"GET",root+"?fields=spreadsheetId,sheets(properties(title,sheetId,gridProperties))")
        if obj.get("spreadsheetId")!=book:
            fail("CATALOG_ID")
        hits=[s.get("properties",{}) for s in obj.get("sheets",[]) if s.get("properties",{}).get("title")==tab]
        if len(hits)!=1:
            fail("TAB_MISSING_OR_AMBIGUOUS")
        p=hits[0]; g=p.get("gridProperties",{})
        n,w=g.get("rowCount"),g.get("columnCount")
        if type(n) is not int or not 1<=n<=LIMITS[tab] or type(w) is not int or w<len(header):
            fail("GRID_BOUND")
        return p.get("sheetId"),n,w
    initial=meta()
    end=chr(64+len(header))
    def read(a,b):
        span="'"+tab+"'!A"+str(a)+":"+end+str(b)
        obj=request(session,"GET",root+"/values/"+urllib.parse.quote(span,safe="")+
                    "?valueRenderOption=UNFORMATTED_VALUE")
        if obj.get("range") not in (span,span.replace("'","")) or obj.get("majorDimension")!="ROWS":
            fail("RANGE_BINDING")
        rows=obj.get("values",[])
        if not isinstance(rows,list) or len(rows)>b-a+1 or any(
                not isinstance(r,list) or len(r)>len(header) for r in rows):
            fail("RANGE_BOUND")
        return rows
    if read(1,1)!=[header]:
        fail("HEADER")
    rows=[header]
    seen=set()
    for a in range(2,initial[1]+1,2000):
        for r in read(a,min(a+1999,initial[1])):
            if not any(str(v if v is not None else "").strip() for v in r):
                continue
            if not cell(r,0).strip():
                fail("UNKEYED_SOURCE_ROW")
            if tab=="CSS Git Ingest":
                key=cell(r,0)
                uid,folder,uv=cell(r,2),cell(r,3),cell(r,4)
                if (key in seen or not folder or "|" in folder
                        or not re.fullmatch(r"\d+",uid) or not re.fullmatch(r"\d+",uv)
                        or key!=folder+"|"+uv+"|"+uid):
                    fail("MAIL_TUPLE_MISMATCH_OR_DUPLICATE")
                seen.add(key)
            rows.append(r)
    if meta()!=initial or read(1,1)!=[header]:
        fail("CATALOG_OR_HEADER_CHANGED")
    return rows


def verified_issued(invoice):
    from tax_invoice_extract import extract
    result=set()
    identities={}
    for r in invoice[1:]:
        subject=cell(r,6)
        if cell(r,10) not in VALID or REPLY.match(subject) or not ISSUE.match(subject):
            continue
        key=exact_key(subject)
        if not key:
            continue
        parsed=extract(cell(r,5))
        try: amount=int(cell(r,1))
        except ValueError:fail("ISSUED_AMOUNT_REVIEW")
        number=cell(r,0)
        if (not parsed or parsed[0]!=number or parsed[4]!=amount or amount<=0
                or not cell(r,8) or instant(cell(r,7)) is None):
            fail("ISSUED_EVIDENCE_REVIEW")
        identity=(key,amount,instant(cell(r,7)))
        if number in identities and identities[number]!=identity:
            fail("ISSUED_IDENTITY_CONFLICT")
        identities[number]=identity
        result.add(key)
    return result


def select_candidates(mail,invoice):
    """Return pending, issued-notice-only and aggregate scope.

    The issued-notice-only dict contains exact original issue notices whose
    filename amount is not verified. Never enqueue them as pending.
    """
    issued=verified_issued(invoice)
    originals={}
    issue_notices={}
    review=Counter()
    for r in mail[1:]:
        if (cell(r,3).upper()!="INBOX" or cell(r,6).lower()!="css@novogene-amea.com"
                or cell(r,15)!="INBOUND" or cell(r,16).strip()):
            continue
        subject=cell(r,9)
        if REPLY.match(subject):
            continue
        is_issue=bool(ISSUE.match(subject))
        if not is_issue and not ready(subject):
            continue
        key=exact_key(subject)
        date=instant(cell(r,5))
        uid,uv=cell(r,2),cell(r,4)
        if not key or date is None or not re.fullmatch(r"\d+",uid) or not re.fullmatch(r"\d+",uv):
            review["NOTICE_REFERENCE_OR_DATE_REVIEW"]+=1
            continue
        item={"key":key,"x":key[5:],"j":key[:4],"date":cell(r,5),"uid":uid,
              "uidvalidity":uv,"subject":subject,"message_id":cell(r,1),
              "ingest_key":cell(r,0)}
        pool=issue_notices if is_issue else originals
        old=pool.get(key)
        if old is None or (date,int(uid))>(instant(old["date"]),int(old["uid"])):
            pool[key]=item
    issue_only={k:r for k,r in issue_notices.items() if k in originals and k not in issued}
    pending={k:r for k,r in originals.items() if k not in issued and k not in issue_only}
    summary={"mail_rows":len(mail)-1,"statement_keys":len(originals),
             "verified_issued_keys":len(set(originals)&issued),
             "pending_candidates":len(pending),"issue_notice_only":len(issue_only),
             "review":dict(review)}
    return pending,issue_only,summary


def same_notice(old,item):
    old_time,new_time=instant(cell(old,5)),instant(item["date"])
    return (old_time is not None and old_time==new_time and
            cell(old,6)==item["uid"] and cell(old,7)==item["uidvalidity"])
