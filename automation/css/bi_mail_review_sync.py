#!/usr/bin/env python3
"""Sync UID-keyed BI review choices with legacy exclusion ledgers (idempotent)."""
import json, os, sys, datetime
from collections import Counter
from google.oauth2 import service_account
from googleapiclient.discovery import build

BOOK=os.getenv("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
SCOPES=["https://www.googleapis.com/auth/spreadsheets"]
REVIEW="BI Mail Review & Exclusions"
SOURCE="Unanswered Emails Auto"
MAIL="Unanswered Email Exclusions"
SENDERS="Unanswered Sender Exclusions"
def auth():
    value=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GCP_SA_KEY") or os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not value:
        raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON (or GCP_SA_KEY) secret")
    try:
        data=json.loads(value)
    except ValueError:
        import base64
        data=json.loads(base64.b64decode(value))
    return build("sheets","v4",credentials=service_account.Credentials.from_service_account_info(data,scopes=SCOPES),cache_discovery=False).spreadsheets()
def get(s,name,range_):
    return s.values().get(spreadsheetId=BOOK,range="'"+name.replace("'","''")+"'!"+range_,valueRenderOption="UNFORMATTED_VALUE").execute().get("values",[])
def batch(s, ranges):
    if ranges: s.values().batchUpdate(spreadsheetId=BOOK,body={"valueInputOption":"RAW","data":[{"range":r,"values":[v]} for r,v in ranges]}).execute()
def append(s, name, entries):
    if entries:s.values().append(spreadsheetId=BOOK,range="'"+name+"'!A1",valueInputOption="RAW",insertDataOption="INSERT_ROWS",body={"values":entries}).execute()
def col(v):return str(v).strip().lower() in ("true","1","yes")
def at(row,i):return row[i] if len(row)>i else ""
def main():
    s=auth();read_only=os.getenv("DRY_RUN","true").lower()!="false"
    review=get(s,REVIEW,"A2:I1250")
    source=get(s,SOURCE,"A2:U1000")
    mail=get(s,MAIL,"A2:L5500")
    sender=get(s,SENDERS,"A2:F1000")
    source_by_uid={str(at(r,17)):r for r in source if at(r,17)}
    review_uid={str(at(r,4)) for r in review if at(r,4)}
    sender_by_addr={str(at(r,1)).lower():i+2 for i,r in enumerate(sender) if at(r,1)}
    mail_by_uid={str(at(r,1)):i+2 for i,r in enumerate(mail) if at(r,1)}
    # Preserve existing exclusion ledgers; only act on explicit reviewer choices.
    to_append_review=[];to_append_mail=[];to_append_sender=[]
    updates=[];processed=[];counts=Counter();ts=datetime.datetime.now(datetime.timezone.utc).isoformat()
    pending_mail=set();pending_sender=set();sender_actions={};uid_actions={}
    # Never overwrite an existing reviewer decision; append new UIDs only.
    for uid,r in source_by_uid.items():
        if uid not in review_uid:
            to_append_review.append(["NONE",at(r,8),at(r,3),at(r,0),uid,at(r,20),"","NOT_SUBMITTED",ts[:10]])
    for i,r in enumerate(review,start=2):
        action=str(at(r,0)).strip().upper();uid=str(at(r,4)).strip();addr=str(at(r,1)).strip().lower()
        state=str(at(r,7)).strip()
        if not uid or action not in {"EXCLUDE_MAIL","EXCLUDE_SENDER","RESTORE_MAIL","RESTORE_SENDER"}:continue
        # Already synchronized decisions are not replayed.
        if state=="SYNCED:"+action:continue
        if action.endswith("SENDER"):
            prior=sender_actions.get(addr)
            if prior and prior!=action:
                counts["conflicting_sender_requests"]+=1
                continue
            sender_actions[addr]=action
        else:
            prior=uid_actions.get(uid)
            if prior and prior!=action:
                counts["conflicting_uid_requests"]+=1
                continue
            uid_actions[uid]=action
        src=source_by_uid.get(uid,[])
        if action.endswith("MAIL"):
            old=mail_by_uid.get(uid)
            if action=="EXCLUDE_MAIL":
                if old and old>0:
                    updates.append(("'"+MAIL+"'!A"+str(old),[False]))
                elif uid not in pending_mail:
                    pending_mail.add(uid)
                    to_append_mail.append([False,uid,"BI reviewer exclude",ts,addr,at(src,3) or at(r,2),at(src,1),at(src,16),at(src,18),ts,"","UID only"])
                    mail_by_uid[uid]=-1
            elif old and old>0:
                updates.append(("'"+MAIL+"'!A"+str(old),[True]))
            else:
                counts["restore_mail_not_found"]+=1
                continue
        elif addr:
            old=sender_by_addr.get(addr)
            if action=="EXCLUDE_SENDER":
                if old and old>0: updates.append(("'"+SENDERS+"'!A"+str(old),[False]))
                elif addr not in pending_sender:
                    pending_sender.add(addr)
                    to_append_sender.append([False,addr,"exact","BI reviewer exclude",ts,0])
                    sender_by_addr[addr]=-1
            elif old and old>0:
                updates.append(("'"+SENDERS+"'!A"+str(old),[True]))
            else:
                counts["restore_sender_not_found"]+=1
                continue
        else:continue
        processed.append((i,action));counts[action]+=1
    print(json.dumps({"dry_run":read_only,"new_inbox":len(to_append_review),"mail_exclusions_new":len(to_append_mail),"sender_exclusions_new":len(to_append_sender),"requested":dict(counts)},ensure_ascii=False))
    if read_only:return
    if counts["conflicting_sender_requests"] or counts["conflicting_uid_requests"]:
        raise RuntimeError("Conflicting review actions detected; resolve before live sync")
    # Apply all writes before recording success. Reruns are safe by UID/address.
    batch(s,updates)
    append(s,MAIL,to_append_mail)
    append(s,SENDERS,to_append_sender)
    append(s,REVIEW,to_append_review)
    batch(s,[("'"+REVIEW+"'!H"+str(i),["SYNCED:"+action]) for i,action in processed])
    print(json.dumps({"synced":len(processed),"new_review_records":len(to_append_review)},ensure_ascii=False))
if __name__=="__main__":
    try:main()
    except Exception as e:
        print(type(e).__name__+": "+str(e),file=sys.stderr)
        sys.exit(1)
