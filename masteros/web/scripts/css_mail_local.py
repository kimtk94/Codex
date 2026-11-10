#!/usr/bin/env python3
"""Loopback-only CSS mail/Lead review worker for the existing local Next.js app.

Reads existing QQ/Lead Sheets. The ONLY writes are explicit reviewer actions
in the two dedicated reply-decision ledgers. No IMAP, SMTP, CRM, or Feishu write.
Called through the guarded Next.js route, not exposed as a public service.
"""
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote
from email.utils import getaddresses

QQ = "1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
SFDC = "1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
QUEUE = "Unanswered Reply Review 60D"
DECISIONS = "Unanswered Reply Decisions"
RULES = "Unanswered Reply Routing Rules"
AUDIT = "Unanswered Reply Audit"
LEADS = "Lead Sent Dates"
KST = dt.timezone(dt.timedelta(hours=9))
UTC = dt.timezone.utc
MAIL_DECISION_HEAD = ["Active (Edit)","Decision","Canonical Ingest Key",
    "Mail UID","Customer Email","Subject","Reviewer Note","Recorded UTC"]
RULE_HEAD = ["Active (Edit)","Rule Type (Edit)","Exact Address (Edit)",
    "Condition","Action","Reviewer Note","Created From Mail","Recorded UTC"]
EDIT_HEAD = ["Receipt Role","Action (Edit)","Rule Target Address (Edit)",
    "Reviewer Note (Edit)","Action State"]
EMAIL = re.compile(r"^[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+$")
KEY = re.compile(r"^[A-Za-z0-9_./|:-]{3,150}$")
ACTIONS = {"SKIP_MAIL","SKIP_CC_TO","SKIP_CC_SENDER",
           "RESTORE_MAIL","RESTORE_RULE"}


def cell(row, n):
    return str(row[n]).strip() if n < len(row) and row[n] is not None else ""


def addresses(value):
    return {address.casefold() for _,address in getaddresses([str(value or "")]) if address}


def address(value):
    x = str(value or "").strip().casefold()
    if not EMAIL.fullmatch(x):
        raise ValueError("EXACT_EMAIL_REQUIRED")
    return x


def owner_email():
    return address(os.environ.get("CSS_LOCAL_MAIL_OWNER",""))


def role(row, owner):
    if owner in addresses(cell(row,12)):
        return "TO"
    if owner in addresses(cell(row,13)):
        return "CC_ONLY"
    return "NOT_OWNER"


def expected_headers(queue, dec, rules, leads):
    if not queue or len(queue[0]) != 24 or queue[0][14] != "Canonical Ingest Key" or queue[0][19:24] != EDIT_HEAD:
        raise ValueError("QQ_REPLY_QUEUE_SCHEMA_MISMATCH")
    if not dec or dec[0] != MAIL_DECISION_HEAD:
        raise ValueError("QQ_REPLY_DECISION_SCHEMA_MISMATCH")
    if not rules or rules[0] != RULE_HEAD:
        raise ValueError("QQ_REPLY_ROUTING_SCHEMA_MISMATCH")
    if not leads or len(leads[0]) != 21 or leads[0][0] != "Lead ID" or leads[0][7] != "Personal Mail Evidence":
        raise ValueError("SFDC_LEAD_DATES_SCHEMA_MISMATCH")


def active_decisions(rows):
    return {cell(r,2) for r in rows[1:] if cell(r,0).upper() in ("TRUE","1","YES")
            and cell(r,1) == "SKIP_MAIL" and cell(r,2)}


def active_rules(rows):
    found = set()
    for r in rows[1:]:
        if cell(r,0).upper() not in ("TRUE","1","YES"):
            continue
        kind = cell(r,1)
        if kind not in ("TO_ADDRESS","SENDER_ADDRESS") or cell(r,3)!="OWNER_CC_ONLY" or cell(r,4)!="SKIP":
            raise ValueError("ACTIVE_RULE_INVALID")
        found.add((kind,address(cell(r,2))))
    return found


def applicable_rule(row, owner, rules):
    if role(row, owner)!="CC_ONLY":
        return ""
    tos=addresses(cell(row,12))
    senders=addresses(cell(row,3))
    if any(("TO_ADDRESS",to) in rules for to in tos):
        return "SKIPPED_CC_TO_RULE"
    if any(("SENDER_ADDRESS",sender) in rules for sender in senders):
        return "SKIPPED_CC_SENDER_RULE"
    return ""


def parsed_time(value):
    try:
        v = str(value or "").replace(" KST","").replace("Z","+00:00").strip()
        t = dt.datetime.fromisoformat(v)
        return t if t.tzinfo else t.replace(tzinfo=KST)
    except ValueError:
        return None


def snapshot(queue, dec, rules, audit, leads, owner, now=None):
    expected_headers(queue,dec,rules,leads)
    now=now or dt.datetime.now(UTC)
    excluded=active_decisions(dec)
    routing=active_rules(rules)
    keyed=set()
    visible=[]
    skipped={"mail":0,"cc_to":0,"cc_sender":0}
    for row in queue[1:]:
        key=cell(row,14)
        if not key:
            continue
        if key in keyed:
            raise ValueError("DUPLICATE_CANONICAL_MAIL_KEY")
        keyed.add(key)
        if key in excluded:
            skipped["mail"]+=1
            continue
        rule=applicable_rule(row,owner,routing)
        if rule:
            skipped["cc_to" if rule=="SKIPPED_CC_TO_RULE" else "cc_sender"]+=1
            continue
        visible.append({
            "key":key,"uid":cell(row,10),"priority":cell(row,0),
            "days":cell(row,1),"received":cell(row,2),
            "sender":cell(row,3),"subject":cell(row,4),
            "project":cell(row,5),"evidence":cell(row,6),
            "recommendation":cell(row,7),"assessment":cell(row,8),
            "to":cell(row,12),"cc":cell(row,13),"role":role(row,owner),
            "queueActionPending":cell(row,20),
        })
    leads_by_id=set()
    lead_list=[]
    status_counts={}
    for row in leads[1:]:
        key=cell(row,0)
        if not key:
            continue
        if key in leads_by_id:
            raise ValueError("DUPLICATE_SFDC_LEAD_ID")
        leads_by_id.add(key)
        state=cell(row,7)
        status_counts[state]=status_counts.get(state,0)+1
        lead_list.append({
            "id":key,"institution":cell(row,1),"name":cell(row,2),
            "email":cell(row,3),"created":cell(row,4),"leadStatus":cell(row,5),
            "owner":cell(row,6),"evidence":state,"afterCount":cell(row,8),
            "firstAfter":cell(row,9),"lastAfter":cell(row,10),
            "everCount":cell(row,11),"firstEver":cell(row,12),
            "lastEver":cell(row,13),"toCount":cell(row,14),
            "ccCount":cell(row,15),"recommendation":cell(row,19),
        })
    metrics={cell(row,0):cell(row,1) for row in audit[1:] if cell(row,0)}
    check=parsed_time(metrics.get("Snapshot UTC"))
    lead_check=parsed_time(cell(leads[1],20)) if len(leads)>1 else None
    def freshness(t):
        if not t:return "UNKNOWN"
        age=(now-t.astimezone(UTC)).total_seconds()
        return "FRESH" if -600<=age<=72*3600 else "STALE"
    return {
        "status":"PASS" if freshness(check)=="FRESH" and freshness(lead_check)=="FRESH" else "STALE",
        "source":"PRIVATE_GOOGLE_SHEETS_METADATA_ONLY",
        "mailSourceStatus":freshness(check),"leadSourceStatus":freshness(lead_check),
        "mailCheckedAt":check.isoformat() if check else "",
        "leadCheckedAt":lead_check.isoformat() if lead_check else "",
        "mailCount":len(visible),"mailTotal":len(keyed),"skipped":skipped,
        "rules":[{"type":kind,"address":addr} for kind,addr in sorted(routing)],
        "ruleCount":len(routing),"mailSkipCount":len(excluded),
        "skippedMails":[{"key":cell(r,2),"uid":cell(r,3),"sender":cell(r,4),
                          "subject":cell(r,5)} for r in dec[1:] if cell(r,0).upper() in ("TRUE","YES","1") and cell(r,1)=="SKIP_MAIL"],
        "leadCount":len(lead_list),"leadStates":status_counts,
        "mail":visible,"leads":lead_list,
    }


def validate_request(body):
    if not isinstance(body,dict) or set(body)-{"mode","action","key","uid","sender","subject","to","cc","target","note"}:
        raise ValueError("REQUEST_FIELDS_INVALID")
    mode=body.get("mode")
    if mode=="snapshot":
        if set(body)!={"mode"}:raise ValueError("READ_REQUEST_INVALID")
        return
    if mode!="decision" or body.get("action") not in ACTIONS:
        raise ValueError("ACTION_NOT_SUPPORTED")
    for field in ("key","uid","sender","subject","to","cc","target","note"):
        if not isinstance(body.get(field,""),str):
            raise ValueError("REQUEST_FIELD_TYPE_INVALID")
    if len(body.get("note",""))>300:
        raise ValueError("NOTE_TOO_LONG")
    if body["action"] in ("SKIP_MAIL","SKIP_CC_TO","SKIP_CC_SENDER","RESTORE_MAIL"):
        if not KEY.fullmatch(body.get("key","")):
            raise ValueError("CANONICAL_KEY_INVALID")
    if body["action"]=="RESTORE_RULE":
        if body.get("target","") not in ("TO_ADDRESS","SENDER_ADDRESS"):
            raise ValueError("RULE_TYPE_REQUIRED")
        address(body.get("sender",""))


def sheet_session():
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
    raw=os.getenv("GCP_SERVICE_ACCOUNT_JSON","").strip()
    if raw:
        data=json.loads(raw)
    else:
        path=Path(os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or
            Path.home()/"CSS_Automation"/"credentials"/"service_account.json")
        if not path.is_file():raise RuntimeError("LOCAL_GOOGLE_CREDENTIALS_MISSING")
        data=json.loads(path.read_text(encoding="utf8"))
    return AuthorizedSession(Credentials.from_service_account_info(
        data,scopes=["https://www.googleapis.com/auth/spreadsheets"]))


def value_url(book,name,area):
    return "https://sheets.googleapis.com/v4/spreadsheets/"+book+"/values/"+quote("'"+name+"'!"+area,safe="")


def fetch(session,book,name,area):
    response=session.get(value_url(book,name,area),timeout=35)
    response.raise_for_status()
    return response.json().get("values",[])


def update_cell(session,book,name,a1,value):
    response=session.put(value_url(book,name,a1)+"?valueInputOption=RAW",
        json={"values":[[value]]},timeout=35)
    response.raise_for_status()


def append_ledger(session,name,values):
    path=value_url(QQ,name,"A1:H2000")+":append?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
    response=session.post(path,json={"values":[values]},timeout=35)
    response.raise_for_status()
    return response.json()


def load(session):
    queue=fetch(session,QQ,QUEUE,"A1:X2000")
    dec=fetch(session,QQ,DECISIONS,"A1:H2000")
    rules=fetch(session,QQ,RULES,"A1:H2000")
    audit=fetch(session,QQ,AUDIT,"A1:C70")
    leads=fetch(session,SFDC,LEADS,"A1:U1600")
    expected_headers(queue,dec,rules,leads)
    return queue,dec,rules,audit,leads


def apply_action(session,body,owner):
    queue,dec,rules,audit,leads=load(session)
    now=dt.datetime.now(UTC)
    summary=snapshot(queue,dec,rules,audit,leads,owner,now)
    if summary["mailSourceStatus"]!="FRESH":
        raise ValueError("MAIL_SNAPSHOT_STALE")
    action=body["action"]
    if action=="RESTORE_RULE":
        typ=body["target"]
        adr=address(body["sender"])
        matches=[i for i,row in enumerate(rules[1:],2)
                 if cell(row,1)==typ and cell(row,2).casefold()==adr
                 and cell(row,0).upper() in ("TRUE","YES","1")]
        if len(matches)!=1:
            raise ValueError("RULE_NOT_UNIQUELY_ACTIVE")
        fresh=fetch(session,QQ,RULES,"A"+str(matches[0])+":E"+str(matches[0]))
        if len(fresh)!=1 or cell(fresh[0],1)!=typ or cell(fresh[0],2).casefold()!=adr or not cell(fresh[0],0).upper() in ("TRUE","YES","1"):
            raise ValueError("RULE_CHANGED_DURING_REVIEW")
        update_cell(session,QQ,RULES,"A"+str(matches[0]),"FALSE")
        return {"status":"PASS","result":"RULE_RESTORED"}
    key=body["key"]
    if action=="RESTORE_MAIL":
        matches=[i for i,r in enumerate(dec[1:],2) if cell(r,2)==key
                 and cell(r,1)=="SKIP_MAIL" and cell(r,0).upper() in ("TRUE","YES","1")]
        if len(matches)!=1:raise ValueError("MAIL_SKIP_NOT_UNIQUELY_ACTIVE")
        fresh=fetch(session,QQ,DECISIONS,"A"+str(matches[0])+":C"+str(matches[0]))
        if len(fresh)!=1 or cell(fresh[0],2)!=key or cell(fresh[0],1)!="SKIP_MAIL" or cell(fresh[0],0).upper() not in ("TRUE","YES","1"):
            raise ValueError("MAIL_DECISION_CHANGED")
        update_cell(session,QQ,DECISIONS,"A"+str(matches[0]),"FALSE")
        return {"status":"PASS","result":"MAIL_RESTORED"}
    originals=[row for row in queue[1:] if cell(row,14)==key]
    if len(originals)!=1:
        raise ValueError("MAIL_NO_LONGER_IN_REVIEW_QUEUE")
    row=originals[0]
    for field,col in (("uid",10),("sender",3),("subject",4),("to",12),("cc",13)):
        if body.get(field,"")!=cell(row,col):
            raise ValueError("MAIL_EVIDENCE_CHANGED")
    # Recheck exact live row before applying a reviewer action.
    if len(queue[1:])>1900:
        raise ValueError("REVIEW_QUEUE_TOO_LARGE")
    note=body.get("note","")[:300]
    stamp=now.isoformat()
    if action=="SKIP_MAIL":
        if key in active_decisions(dec):
            return {"status":"PASS","result":"ALREADY_SKIPPED"}
        record=["TRUE","SKIP_MAIL",key,cell(row,10),cell(row,3),cell(row,4),note,stamp]
        append_ledger(session,DECISIONS,record)
        after=fetch(session,QQ,DECISIONS,"A1:H2000")
        if key not in active_decisions(after):raise RuntimeError("MAIL_DECISION_READBACK_FAILED")
        return {"status":"PASS","result":"MAIL_SKIPPED"}
    if role(row,owner)!="CC_ONLY":
        raise ValueError("CC_ONLY_RULE_REQUIRES_CC_RECIPIENT")
    if action=="SKIP_CC_TO":
        adr=address(body.get("target",""))
        if adr==owner or adr not in addresses(cell(row,12)):
            raise ValueError("TO_ADDRESS_MUST_MATCH_CURRENT_MAIL")
        typ="TO_ADDRESS"
    else:
        senders=addresses(cell(row,3))
        if len(senders)!=1:
            raise ValueError("ONE_SENDER_REQUIRED")
        adr=address(next(iter(senders)))
        typ="SENDER_ADDRESS"
        if body.get("target") and address(body["target"])!=adr:
            raise ValueError("SENDER_RULE_TARGET_MISMATCH")
    if (typ,adr) in active_rules(rules):
        return {"status":"PASS","result":"ALREADY_ACTIVE"}
    record=["TRUE",typ,adr,"OWNER_CC_ONLY","SKIP",note,key,stamp]
    append_ledger(session,RULES,record)
    after=fetch(session,QQ,RULES,"A1:H2000")
    if (typ,adr) not in active_rules(after):
        raise RuntimeError("ROUTING_RULE_READBACK_FAILED")
    return {"status":"PASS","result":"CC_RULE_CREATED"}


def main():
    raw=sys.stdin.read(1600)
    body=json.loads(raw)
    validate_request(body)
    owner=owner_email()
    session=sheet_session()
    if body["mode"]=="snapshot":
        data=snapshot(*load(session),owner)
        print(json.dumps(data,ensure_ascii=False,separators=(",",":")))
    else:
        result=apply_action(session,body,owner)
        print(json.dumps(result,ensure_ascii=False,separators=(",",":")))


if __name__=="__main__":
    try:main()
    except Exception as error:
        # Never reveal customer mail, addresses, OAuth keys, or filesystem paths.
        code=str(error) if isinstance(error,ValueError) else type(error).__name__
        if len(code)>70 or re.search(r"[/\\@:\s]",code):
            code=type(error).__name__
        print(json.dumps({"status":"BLOCK","code":code},separators=(",",":")))
        sys.exit(1)
