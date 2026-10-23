#!/usr/bin/env python3
"""Read-only Salesforce quote readiness and follow-up priority audit.

Reject incomplete Salesforce exports; never infer Active from Opportunity stage.
"""
import datetime as dt
import os, sys
import incremental_sync as css
from unified_followup_sync import base, get, put, ensure, KST, DST
REQUIRED={"salesforce record id":["salesforce record id","quote id","sfdc quotation id"],"active":["active","isactive","is active"],"amount":["total amount","grand total","quotation total","quote amount"],"currency":["currency","currencyisocode","quote currency"],"opportunity id":["opportunity id","related opportunity id"]}
def missing(headers):
    names={" ".join(str(h).lower().replace("_"," ").split()) for h in headers}
    return [name for name,options in REQUIRED.items() if not any(opt in names for opt in options)]
def main():
    session=css.authorize()
    rows=get(session,DST,"Quotation","A1:Z1000")
    if not rows:raise RuntimeError("SFDC_QUOTATION_SOURCE_NOT_FOUND")
    absent=missing(rows[0])
    ensure(session,DST,"Automation Health")
    t=dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    status="BLOCKED_EXPORT_MISSING_FIELDS" if absent else "SCHEMA_READY_PENDING_RECORD_VALIDATION"
    put(session,DST,"Automation Health","A3",[["SFDC Quote",t,status,", ".join(absent) if absent else "Validate individual records against Salesforce"]])
    print("SFDC_ACTIVE_VALIDATION "+status+" missing="+str(len(absent))+" quote_rows="+str(len(rows)-1))
if __name__=="__main__":main()
