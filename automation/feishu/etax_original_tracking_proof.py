#!/usr/bin/env python3
"""Read-only Feishu original eTax tracking-sheet issuance-proof audit.

Feishu Latest eTax's XLOOKUP formula refers to a different spreadsheet,
Tracking file 2026, columns D (invoice ID) and H (tracking state). Formula
text is not proof. Read the original, not its mirror, without mutations.

ERP/CMS invoice ID and tracking status are not evidence of month-end financial
recognition or independently certified owner. Never auto-post Revenue.
"""
import re
import sys
import urllib.parse

from qq_mail_ingest import api, SafeError, auth

TRACKING_TOKEN="WI6msu7UihcZQotx8XKjDbFypvh"
TRACKING_TAB="Tracking file 2026"
MAX_ROWS=5000
TARGETS={
    "20910000203":"OCT_MANUAL_28_567M_GROSS",
    "20910000208":"OCT_MANUAL_1_287M_GROSS",
    "20910000209":"OCT_MANUAL_9_317M_GROSS",
    "20910000197":"OCT_POSSIBLE_DUPLICATE_4_5265M_GROSS",
    "209126001032":"OCT_CMS_SAME_PROJECT_AMOUNT",
    "209126000887":"OCT_UNLINKED_QQ_GAP_12_012M",
    "209126000926":"OCT_UNLINKED_QQ_GAP_1_47015M",
    "209126000984":"OCT_UNLINKED_QQ_GAP_4_4385M",
    "209126001007":"OCT_UNLINKED_QQ_GAP_1_969M",
}


def scalar(value):
    if value is None:return ""
    if isinstance(value,str):return value.strip()
    if isinstance(value,(int,float)):
        return str(int(value)) if float(value).is_integer() else str(value)
    if isinstance(value,dict):
        return scalar(value.get("value") or value.get("text") or "")
    if isinstance(value,list):
        return " ".join(scalar(x) for x in value).strip()
    return ""


def classify_status(value):
    """Only exact recognized values, never blanket nonempty=issued."""
    state=scalar(value).upper().strip()
    if not state or state.startswith("="):
        return "UNKNOWN_NO_TRUSTED_STATUS"
    if state in {"YES","Y","ISSUED","已开票","已开具","已开","DONE","COMPLETED"}:
        return "TRACKING_MARKED_ISSUED_NOT_ACCOUNTING_PROOF"
    if state in {"NO","N","NOT ISSUED","UNISSUED","未开票","待开票","PENDING"}:
        return "TRACKING_MARKED_NOT_ISSUED"
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}(?:[ T].*)?",state):
        return "TRACKING_DATE_PRESENT_VERIFY_DATE_TYPE"
    return "TRACKING_VALUE_UNRECOGNIZED_REVIEW"


def build_index(values):
    """Requested A1 range starts at D; row[0] is D, row[4] is H."""
    seen={}
    if len(values)>MAX_ROWS:
        raise SafeError("TRACKING_RANGE_EXCEEDS_HARD_LIMIT")
    for n,row in enumerate(values,1):
        if not isinstance(row,list):
            raise SafeError("TRACKING_INVALID_ROW_SHAPE")
        invoice=scalar(row[0]) if row else ""
        if invoice not in TARGETS:continue
        status=scalar(row[4]) if len(row)>4 else ""
        if invoice in seen:
            raise SafeError("TRACKING_DUPLICATE_INVOICE_ID:"+invoice)
        seen[invoice]=(status,n)
    return seen


def read_tracking(token):
    s=urllib.parse.quote(TRACKING_TOKEN,safe="")
    sheets=api("GET",f"/open-apis/sheets/v3/spreadsheets/{s}/sheets/query",
               token,action="etax_tracking_sheet_catalog")
    matches=[x for x in sheets.get("sheets") or []
             if x.get("title")==TRACKING_TAB]
    if len(matches)!=1 or not matches[0].get("sheet_id"):
        raise SafeError("TRACKING_TAB_INACCESSIBLE_OR_MISSING")
    sid=matches[0]["sheet_id"]
    interval=urllib.parse.quote(f"{sid}!D1:H{MAX_ROWS}",safe="")
    data=api("GET",f"/open-apis/sheets/v2/spreadsheets/{s}/values/{interval}",
             token,action="etax_tracking_cells_read")
    range_=data.get("valueRange") or {}
    return range_.get("values") or [],data.get("revision")


def main():
    token,_=auth()
    rows,revision=read_tracking(token)
    indexed=build_index(rows)
    if not rows:raise SafeError("TRACKING_SOURCE_EMPTY")
    states={}
    for invoice,kind in TARGETS.items():
        value,line=indexed.get(invoice,("",0))
        state=classify_status(value) if line else "NOT_IN_TRACKING"
        states[invoice]=state
        print("ETAX_TRACKING_PROOF invoice="+invoice+
              " case="+kind+" matched="+str(bool(line)).lower()+
              " status="+state,flush=True)
    print("ETAX_TRACKING_AUDIT rows_read="+str(len(rows))+
          " keys_matched="+str(len(indexed))+
          " revision_present="+str(revision is not None)+
          " original_sheet_read=YES sheet_mutations=0 "+
          "revenue_mutations=0 owner_attribution=NOT_PROVEN",flush=True)
    if any(state.startswith(("NOT_IN","UNKNOWN","TRACKING_VALUE_UNRECOGNIZED"))
           for state in states.values()):
        print("ETAX_TRACKING_DECISION=HOLD_MANUAL_REVENUE_UNTIL_ISSUANCE_"+
              "MONTH_OWNER_AND_DEDUP_RECONCILED",flush=True)
    else:
        print("ETAX_TRACKING_DECISION=TRACKING_STATES_READ_"+
              "NO_AUTOMATIC_REVENUE_PROMOTION",flush=True)


if __name__=="__main__":
    try:main()
    except Exception as exc:
        code=str(exc) if isinstance(exc,SafeError) else type(exc).__name__
        print("ETAX_TRACKING_PROOF_FAILED="+code,file=sys.stderr)
        sys.exit(1)
