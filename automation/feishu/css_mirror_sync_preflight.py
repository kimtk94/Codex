#!/usr/bin/env python3
"""Conditional Feishu generated-mirror refresh before CSS P0 structural parity.

No Feishu writes, no customer decisions, no invoices/revenue settlement.
Only replace the five authorized generated mirror tabs and manifest when the
latest source identifier/date/record count changed and all sources passed
the existing structural selection gates. Never mask a raw source failure.
"""
import json
import os
import sys
import urllib.parse

FIELDS=["Source","Source Date","Synced At KST","Source ID","Rows","Schema","Meaning"]
SCHEMAS={"Payment Outstanding":"HEADER_MATCHED",
         "Payment Receipt":"HEADER_MATCHED",
         "Prepayments":"HEADER_MATCHED",
         "eTax Invoice":"HEADER_MATCHED",
         "Online-Project":"BASE_FIELDS"}

def txt(row,index):
    return str(row[index]).strip() if index<len(row) and row[index] is not None else ""

def preflight(snapshots,manifest):
    if set(snapshots)!=set(SCHEMAS):
        raise ValueError("INCOMPLETE_FEISHU_SOURCE_SET")
    for source,item in snapshots.items():
        if item.get("schema")!=SCHEMAS[source]:
            raise ValueError("REFUSE_UNRECOGNIZED_SOURCE_SCHEMA_"+source)
        if not item.get("source_id") or not item.get("source_date"):
            raise ValueError("SOURCE_VERSION_NOT_IDENTIFIED_"+source)
        if not item.get("rows") or not item.get("headers"):
            raise ValueError("SOURCE_DATA_MISSING_"+source)
        if len(set(item["headers"]))!=len(item["headers"]):
            raise ValueError("DUPLICATE_SOURCE_COLUMN_"+source)
    if not manifest:return ["MANIFEST_MISSING"]
    if [txt(manifest[0],i) for i in range(len(FIELDS))]!=FIELDS:
        raise ValueError("MIRROR_MANIFEST_FOREIGN_SCHEMA")
    by={}
    for row in manifest[1:]:
        source=txt(row,0)
        if not source:continue
        if source not in SCHEMAS or source in by:
            raise ValueError("MIRROR_MANIFEST_FOREIGN_OR_DUPLICATE_SOURCE")
        by[source]=row
    reasons=[]
    for source,item in snapshots.items():
        row=by.get(source)
        if row is None:
            reasons.append(source+":MISSING")
            continue
        checks=[(txt(row,1),item["source_date"],"SOURCE_DATE"),
                (txt(row,3),item["source_id"],"SOURCE_ID"),
                (txt(row,4),str(len(item["rows"])),"ROW_COUNT"),
                (txt(row,5),item["schema"],"SCHEMA")]
        reasons.extend(source+":"+label for old,new,label in checks if old!=str(new))
    return reasons

def main():
    from latest_source_sync import collect,publish
    from project_status_sync import google,api
    if os.getenv("GITHUB_REPOSITORY")!="kimtk94/Codex" or not os.getenv("GITHUB_RUN_ID","").isdigit():
        raise RuntimeError("UNTRUSTED_GITHUB_ACTION_CONTEXT")
    session=google()
    prefix="/values/"+urllib.parse.quote("'Feishu Source Manifest'!A1:G10",safe="")
    existing=api(session,"GET",prefix).get("values",[])
    # Read all five original Feishu snapshots and validate before altering any
    # generated Google Sheets tab; the raw source remains read-only.
    snapshots=collect()
    reasons=preflight(snapshots,existing)
    if not reasons:
        print("CSS_FEISHU_PREFLIGHT_ALREADY_CURRENT sources=5 generated_writes=0")
        return
    print("CSS_FEISHU_PREFLIGHT_REFRESH_NEEDED changed="+
          ",".join(sorted(reasons))+"; no raw writes or payment certification")
    publish(session,snapshots)
    observed=api(session,"GET",prefix).get("values",[])
    if preflight(snapshots,observed):
        raise RuntimeError("POST_REFRESH_SOURCE_PARITY_FAILED")
    print("CSS_FEISHU_PREFLIGHT_SYNCED sources=5 generated_mirrors_only=true")
    print("NO_INVOICE_APPROVAL_NO_PAYMENT_APPROVAL_NO_REVENUE_BOOKING")

if __name__=="__main__":
    try:main()
    except Exception as err:
        print("CSS_FEISHU_PREFLIGHT_FAILED="+type(err).__name__,file=sys.stderr)
        sys.exit(1)
