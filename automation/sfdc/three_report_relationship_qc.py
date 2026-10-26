#!/usr/bin/env python3
"""Audit independently staged Salesforce relationships. No business-sheet writes."""
import collections
import json
import os
import sys
import urllib.parse
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from three_report_email_ingest import SHEET, SCHEMAS, request

def make_index(header):
    return {v.strip().casefold(): i for i,v in enumerate(header)}

def field(row, columns, name):
    idx=columns.get(name.casefold())
    return row[idx].strip() if idx is not None and idx < len(row) else ""

def compare(leads, opportunities, quotations):
    lh, lr=leads[0], leads[1:]
    oh, op=opportunities[0], opportunities[1:]
    qh, qr=quotations[0], quotations[1:]
    li, oi, qi=make_index(lh),make_index(oh),make_index(qh)
    known_opportunities={field(row,oi,"Opportunity ID") for row in op if field(row,oi,"Opportunity ID")}
    known_leads={field(row,li,"Lead ID") for row in lr if field(row,li,"Lead ID")}
    joined_opportunities=[field(row,qi,"Opportunity ID") for row in qr]
    missing_quote_opportunity=sum(not x for x in joined_opportunities)
    orphan_quote_rows=sum(bool(x) and x not in known_opportunities for x in joined_opportunities)
    quote_ids={field(r,qi,"SFDC Quotation ID") for r in qr if field(r,qi,"SFDC Quotation ID")}
    quote_unlinked_ids={field(r,qi,"SFDC Quotation ID") for r in qr if not field(r,qi,"Opportunity ID") or field(r,qi,"Opportunity ID") not in known_opportunities}
    converted=[field(row,oi,"Lead Converted ID") for row in op if field(row,oi,"Lead Converted ID")]
    lead_orphans=sum(value not in known_leads for value in converted)
    return {"lead_rows":len(lr),"opportunity_rows":len(op),"quotation_process_rows":len(qr),
            "unique_quote_ids":len(quote_ids),"linked_quote_rows":len(qr)-missing_quote_opportunity-orphan_quote_rows,
            "quote_rows_missing_opp_id":missing_quote_opportunity,
            "quote_rows_opp_not_in_export":orphan_quote_rows,
            "unique_quote_ids_with_link_issue":len(quote_unlinked_ids),
            "opportunities_with_lead_id":len(converted),
            "opportunities_without_matching_export_lead":lead_orphans,
            "qc":"REVIEW" if missing_quote_opportunity or orphan_quote_rows else "PASS"}

def read_tab(session,name):
    a1=urllib.parse.quote("'" + name + "'!A1:AZ8000",safe="")
    matrix=request(session,"GET","/values/"+a1).get("values",[])
    if len(matrix)<2:
        raise ValueError("EMPTY_STAGE_"+name)
    return matrix

def main():
    credentials=service_account.Credentials.from_service_account_info(json.loads(os.environ["GCP_SERVICE_ACCOUNT_JSON"]),scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    session=AuthorizedSession(credentials)
    tabs=request(session,"GET","?fields=sheets.properties.title")
    existing={s["properties"]["title"] for s in tabs.get("sheets",[])}
    missing=[obj for obj,cfg in SCHEMAS.items() if cfg["tab"] not in existing]
    if missing:
        print("SFDC_RELATIONSHIP_QC_PENDING_STAGE="+",".join(missing))
        return
    sources={kind:read_tab(session,cfg["tab"]) for kind,cfg in SCHEMAS.items()}
    audit=compare(sources["Leads"],sources["Opportunities"],sources["Quotation"])
    print("SFDC_RELATIONSHIP_QC="+json.dumps(audit,sort_keys=True))
    # Explicit REVIEW does not overwrite staging or existing dashboards.
    if audit["qc"]=="REVIEW":
        print("SFDC_RELATIONSHIP_REQUIRES_REVIEW=true")

if __name__=="__main__":
    main()
