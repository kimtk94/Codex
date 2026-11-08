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
import datetime as dt
import urllib.parse

from qq_mail_ingest import api, SafeError, auth

TRACKING_TOKEN="WI6msu7UihcZQotx8XKjDbFypvh"
TRACKING_TAB="Tracking file 2026"
PAGE_ROWS=1000
MAX_ROWS=20000
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
    if re.fullmatch(r"20\d{2}[-./]\d{1,2}[-./]\d{1,2}(?:[ T].*)?",state):
        return "TRACKING_DATE_PRESENT_VERIFY_DATE_TYPE"
    if re.fullmatch(r"4[4-9]\d{3}(?:\.0+)?",state):
        return "TRACKING_EXCEL_DATE_SERIAL_VERIFY_DATE_TYPE"
    if any(word in state for word in ("已开票","已开具","已开","발행","开票","ISSUED","완료")):
        return "TRACKING_ISSUANCE_WORD_REVIEW_DETAILS"
    if any(word in state for word in ("未开票","未开","미발행","待开","NOT ISSUED","CANCEL")):
        return "TRACKING_NEGATIVE_WORD_REVIEW_DETAILS"
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
    sheet=matches[0]
    sid=sheet["sheet_id"]
    n=(sheet.get("grid_properties") or {}).get("row_count")
    if not isinstance(n,int) or not 1<=n<=MAX_ROWS:
        raise SafeError("TRACKING_FULL_ROW_COVERAGE_NOT_PROVABLE")
    all_rows=[]
    revisions=[]
    for first in range(1,n+1,PAGE_ROWS):
        last=min(n,first+PAGE_ROWS-1)
        interval=urllib.parse.quote(f"{sid}!D{first}:H{last}",safe="")
        data=api("GET",f"/open-apis/sheets/v2/spreadsheets/{s}/values/{interval}",
                 token,action="etax_tracking_cells_read")
        if not isinstance(data.get("valueRange"),dict):
            raise SafeError("TRACKING_RANGE_RESPONSE_MISSING")
        segment=data["valueRange"].get("values") or []
        if not isinstance(segment,list) or len(segment)>last-first+1:
            raise SafeError("TRACKING_RANGE_ROW_COUNT_INVALID")
        all_rows.extend(segment)
        all_rows.extend([[] for _ in range(last-first+1-len(segment))])
        revisions.append(data.get("revision"))
    if len(all_rows)!=n:raise SafeError("TRACKING_FULL_ROW_COVERAGE_INCOMPLETE")
    if len(set(v for v in revisions if v is not None))>1:
        raise SafeError("TRACKING_CHANGED_DURING_READ_RETRY")
    print("ETAX_TRACKING_FULL_COVERAGE rows_declared="+str(n)+
          " rows_scanned="+str(len(all_rows))+
          " pages="+str(len(revisions)),flush=True)
    return all_rows,revisions[0] if revisions else None


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
        if line and state=="TRACKING_VALUE_UNRECOGNIZED_REVIEW":
            raw=scalar(value)
            characters=("NUMERIC" if re.fullmatch(r"[0-9.]+",raw) else
                        "LATIN_TEXT" if re.fullmatch(r"[A-Za-z ._/-]+",raw) else
                        "NON_LATIN_OR_MIXED")
            print("ETAX_TRACKING_STATUS_SHAPE invoice="+invoice+
                  " characters="+characters+
                  " length="+str(len(raw))+
                  " no_raw_value_logged=true",flush=True)
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
