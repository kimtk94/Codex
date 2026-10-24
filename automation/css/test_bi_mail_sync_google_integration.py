#!/usr/bin/env python3
"""Exercise real BI exclusion-sync code on disposable tabs only.

Does not edit customer records or existing legacy exclusion ledgers.
"""
import contextlib
import datetime
import io
import json
import os
import secrets
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
import bi_mail_review_sync as sync

def main():
    raw=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or os.environ.get("GCP_SA_KEY")
    if not raw:
        raise RuntimeError("No Google service-account credentials")
    creds=service_account.Credentials.from_service_account_info(json.loads(raw),scopes=sync.SCOPES)
    api=build("sheets","v4",credentials=creds,cache_discovery=False).spreadsheets()
    tag=secrets.token_hex(5)
    names={key:"_BI_SYNC_TEST_"+key+"_"+tag for key in ("REVIEW","SOURCE","MAIL","SENDERS")}
    ids=[]
    book=os.environ["CSS_SHEET_ID"]
    def vals(tab,rect):
        return api.values().get(spreadsheetId=book,range="'"+tab+"'!"+rect,valueRenderOption="UNFORMATTED_VALUE").execute().get("values",[])
    def put(tab,rect,rows):
        api.values().update(spreadsheetId=book,range="'"+tab+"'!"+rect,valueInputOption="RAW",body={"values":rows}).execute()
    try:
        resp=api.batchUpdate(spreadsheetId=book,body={"requests":[{"addSheet":{"properties":{"title":name,"gridProperties":{"rowCount":30,"columnCount":26}}}} for name in names.values()]}).execute()
        ids=[r["addSheet"]["properties"]["sheetId"] for r in resp["replies"]]
        uid1="probe_mail_"+tag
        uid2="probe_sender_"+tag
        uid3="probe_new_"+tag
        addr="bi-sync-probe@example.invalid"
        def sr(uid):
            x=[""]*21
            x[0]="3일"
            x[1]="2026-10-24 10:00"
            x[3]="Isolated test email"
            x[8]=addr
            x[16]="isolated test email"
            x[17]=uid
            x[20]="CUSTOMER_REVIEW"
            return x
        put(names["SOURCE"],"A2:U4",[sr(uid1),sr(uid2),sr(uid3)])
        put(names["REVIEW"],"A2:I3",[
            ["EXCLUDE_MAIL",addr,"Subject",3,uid1,"REVIEW_2D","","NOT_SUBMITTED","2026-10-24"],
            ["EXCLUDE_SENDER",addr,"Subject",3,uid2,"REVIEW_2D","","NOT_SUBMITTED","2026-10-24"]
        ])
        original={key:getattr(sync,key) for key in names}
        original_auth=sync.auth
        try:
            for key,name in names.items():
                setattr(sync,key,name)
            sync.auth=lambda:api
            os.environ["DRY_RUN"]="false"
            def run():
                with contextlib.redirect_stdout(io.StringIO()) as buf:
                    sync.main()
                return buf.getvalue()
            run()
            mails=vals(names["MAIL"],"A2:L8")
            senders=vals(names["SENDERS"],"A2:F8")
            inbox=vals(names["REVIEW"],"A2:I10")
            assert len(mails)==1 and str(mails[0][1])==uid1, "Mail exclusion append failed"
            assert len(senders)==1 and senders[0][1]==addr, "Sender exclusion append failed"
            assert sum(1 for r in inbox if len(r)>4 and r[4]==uid3)==1, "New UID append failed"
            run()
            assert len(vals(names["MAIL"],"A2:L8"))==1, "Mail duplicated on rerun"
            assert len(vals(names["SENDERS"],"A2:F8"))==1, "Sender duplicated on rerun"
            assert sum(1 for r in vals(names["REVIEW"],"A2:I10") if len(r)>4 and r[4]==uid3)==1, "Review duplicated on rerun"
            put(names["REVIEW"],"A2:A3",[["RESTORE_MAIL"],["RESTORE_SENDER"]])
            run()
            m=vals(names["MAIL"],"A2:A2")
            s=vals(names["SENDERS"],"A2:A2")
            assert m==[[True]] and s==[[True]], "Restore did not set true"
            print(json.dumps({"integration":"PASS","write_scope":"temporary_tabs_only","mail_exclude":"PASS","sender_exclude":"PASS","new_uid":"PASS","idempotency":"PASS","restore":"PASS"},ensure_ascii=False))
        finally:
            sync.auth=original_auth
            for key,value in original.items():
                setattr(sync,key,value)
    finally:
        if ids:
            api.batchUpdate(spreadsheetId=book,body={"requests":[{"deleteSheet":{"sheetId":sid}} for sid in ids]}).execute()
if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print(type(exc).__name__+": "+str(exc),file=sys.stderr)
        sys.exit(1)
