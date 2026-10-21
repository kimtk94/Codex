#!/usr/bin/env python3
"""Read-only SFDC invoice -> Quote status audit. Aggregate output only."""
import os,sys,json,urllib.parse
from collections import Counter
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from invoice_reconciliation import norm_id

SHEET_ID=os.environ.get("SFDC_OUTPUT_SHEET_ID","1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
NAMES={"Quotation Approvals":"A1:W2000","Quotation Invoice Match":"A1:J2000","SFDC Active Quote Links":"A1:L2000"}

def load(session,title,rng):
    target=urllib.parse.quote("'"+title+"'!"+rng,safe="")
    u="https://sheets.googleapis.com/v4/spreadsheets/"+SHEET_ID+"/values/"+target
    r=session.get(u,timeout=50)
    if not r.ok:raise RuntimeError("SHEETS_READ_HTTP_"+str(r.status_code))
    matrix=r.json().get("values",[])
    if not matrix:raise RuntimeError("EMPTY_SOURCE_TAB")
    cols=[str(v).strip() for v in matrix[0]]
    if not cols or len(set(cols))!=len(cols):raise RuntimeError("INVALID_SOURCE_HEADER")
    return [dict(zip(cols,list(row)+[""]*(len(cols)-len(row)))) for row in matrix[1:] if any(str(v).strip() for v in row)]

def audit(approvals,matches,active):
    lookup={}
    for item in approvals:
        key=norm_id(item.get("quotation_id"))
        if key:lookup.setdefault(key,set()).add(str(item.get("salesforce_record_id") or "").strip())
    outcomes=Counter()
    for item in matches:
        key=norm_id(item.get("quotation_id"))
        if not key:
            outcomes["MISSING_QUOTATION_ID"]+=1
        elif key not in lookup:
            outcomes["NOT_IN_APPROVALS"]+=1
        elif len(lookup[key])!=1 or "" in lookup[key]:
            outcomes["AMBIGUOUS_SFDC_QUOTE_ID"]+=1
        else:
            outcomes["QUOTE_ID_RESOLVED"]+=1
    active_true=sum(1 for x in active if str(x.get("is_active","")).lower().strip() in ("true","yes","1"))
    active_unknown=sum(1 for x in active if not str(x.get("is_active","")).strip())
    return {"INVOICE_MATCH_ROWS":len(matches),"APPROVAL_ROWS":len(approvals),
      "ACTIVE_LINK_ROWS":len(active),"ACTIVE_TRUE_EVIDENCE_ROWS":active_true,
      "ACTIVE_UNKNOWN_ROWS":active_unknown,
      "OPPORTUNITY_ID_PRESENT_ROWS":sum(bool(str(x.get("opportunity_id","")).strip()) for x in active),
      "QUOTE_LINK_RESULT_COUNTS":dict(sorted(outcomes.items())),
      "CONTACT_ATTRIBUTIONS":0,"SOURCE_WRITES":0}

def main():
    secret=os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if not secret:raise RuntimeError("GCP_SERVICE_ACCOUNT_JSON_MISSING")
    credentials=service_account.Credentials.from_service_account_info(json.loads(secret),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(credentials)
    data={k:load(session,k,rng) for k,rng in NAMES.items()}
    summary=audit(data["Quotation Approvals"],data["Quotation Invoice Match"],data["SFDC Active Quote Links"])
    print("QUOTE_AUDIT:",json.dumps(summary,sort_keys=True))
    print("QUOTE_STATUS_AUDIT: PASS")
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("QUOTE_STATUS_AUDIT_FAILED:",str(e) if isinstance(e,RuntimeError) else type(e).__name__,file=sys.stderr)
        sys.exit(1)
