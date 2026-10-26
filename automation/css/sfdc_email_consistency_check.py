#!/usr/bin/env python3
"""Validate SFDC and QQ mail UIDs and decisions before marking a run successful."""
import os, json, base64, sys
from google.oauth2 import service_account
from googleapiclient.discovery import build

SFDC=os.getenv("SFDC_SHEET_ID","1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
QQ=os.getenv("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
def col(row,n):
    return str(row[n]).strip() if len(row)>n and row[n] is not None else ""
def indexed(rows,index):
    vals=[col(r,index) for r in rows[1:] if col(r,index)]
    if len(vals)!=len(set(vals)):
        raise RuntimeError("Duplicate UIDs in source")
    return set(vals)
def main():
    raw=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:raise RuntimeError("Missing Google credentials")
    try:key=json.loads(raw)
    except ValueError:key=json.loads(base64.b64decode(raw))
    api=build("sheets","v4",credentials=service_account.Credentials.from_service_account_info(
        key,scopes=["https://www.googleapis.com/auth/spreadsheets"]),cache_discovery=False).spreadsheets().values()
    def read(book,tab,area):
        return api.get(spreadsheetId=book,range="'"+tab+"'!"+area,valueRenderOption="FORMATTED_VALUE").execute().get("values",[])
    qq_mails=read(QQ,"BI Unanswered Triage","A1:U1200")
    sf_mails=read(SFDC,"Unanswered Emails","A1:U1000")
    qq_decisions=read(QQ,"BI Mail Review & Exclusions","A1:J1300")
    sf_decisions=read(SFDC,"Email Review Decisions","A1:J1300")
    if any(not t for t in (qq_mails,sf_mails,qq_decisions,sf_decisions)):
        raise RuntimeError("Missing expected review sheet")
    if col(qq_mails[0],8)!="Thread UID" or col(sf_mails[0],8)!="Thread UID":
        raise RuntimeError("Unexpected mail snapshot column layout")
    if col(qq_decisions[0],4)!="Mail UID (Key)" or col(sf_decisions[0],4)!="Mail UID (Key)":
        raise RuntimeError("Unexpected decision column layout")
    if len(qq_mails)<2 or len(sf_mails)<2:
        raise RuntimeError("Empty mail snapshot cannot be certified PASS")
    if indexed(qq_mails,8)!=indexed(sf_mails,8):
        raise RuntimeError("Email UIDs differ between QQ and SFDC")
    def decisions(rows):
        result={}
        for r in rows[1:]:
            uid=col(r,4)
            if uid:
                if uid in result:raise RuntimeError("Duplicate decision UID")
                result[uid]=col(r,0).upper()
        return result
    q=decisions(qq_decisions);s=decisions(sf_decisions)
    if q!=s:raise RuntimeError("Decision UIDs or choices differ between QQ and SFDC")
    print(json.dumps({"consistency":"PASS","mail_uids":len(indexed(qq_mails,8)),"decisions":len(q)}))
if __name__=="__main__":
    try:main()
    except Exception as e:
        print(type(e).__name__+": "+str(e),file=sys.stderr)
        sys.exit(1)
