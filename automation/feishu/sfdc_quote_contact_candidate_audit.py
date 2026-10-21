#!/usr/bin/env python3
"""Read-only candidate Quote -> Opportunity Name -> Main Contact audit.

No contact assignments are asserted without unique relationship + Active evidence.
Aggregated metrics only. Reuses SFDC Google Sheets read-only authentication.
"""
import json,os,sys
from collections import Counter
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from sfdc_quote_status_audit import load,SHEET_ID

def norm(x):return " ".join(str(x or "").casefold().split())

def audit(links, opportunities):
    lookup={}
    for item in opportunities:
        key=norm(item.get("Opportunity Name"))
        if key:lookup.setdefault(key,[]).append(item)
    counts=Counter()
    for q in links:
        name=norm(q.get("matched_opportunity_name"))
        if not name:
            counts["NO_OPPORTUNITY_NAME"]+=1
            continue
        candidates=lookup.get(name,[])
        if len(candidates)==0:counts["NO_EXACT_NAME_CANDIDATE"]+=1
        elif len(candidates)>1:counts["AMBIGUOUS_OPPORTUNITY_NAME"]+=1
        elif not str(candidates[0].get("Main Contact","")).strip():
            counts["UNIQUE_OPPORTUNITY_NO_CONTACT"]+=1
        else:counts["UNIQUE_NAME_WITH_CONTACT_CANDIDATE"]+=1
        # Name equality is not a stable Salesforce relationship.
    counts["TOTAL_LINK_ROWS"]=len(links)
    counts["VERIFIED_CONTACT_ATTRIBUTIONS"]=0
    counts["BASE_WRITES"]=0
    return dict(sorted(counts.items()))

def main():
    secret=os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if not secret:raise RuntimeError("GCP_SERVICE_ACCOUNT_JSON_MISSING")
    credentials=service_account.Credentials.from_service_account_info(json.loads(secret),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(credentials)
    links=load(session,"SFDC Active Quote Links","A1:L2000")
    opportunities=load(session,"SFDC Opportunity Raw","A1:M2000")
    print("QUOTE_CONTACT_CANDIDATE_AUDIT:",json.dumps(audit(links,opportunities),sort_keys=True))
    print("QUOTE_CONTACT_CANDIDATE_AUDIT: PASS")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("QUOTE_CONTACT_CANDIDATE_AUDIT_FAILED:",str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__,file=sys.stderr)
        sys.exit(1)
