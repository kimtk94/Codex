#!/usr/bin/env python3
"""Inspect only header shape of newest four Feishu Sheets tabs; never print cell values."""
import datetime as dt
import hashlib
import os
import sys
import urllib.parse
from zoneinfo import ZoneInfo
from sheets_tab_discovery import api, TOKEN
from latest_four_formats import select

def header_fingerprint(header):
    """Return only structural evidence; never disclose raw header labels."""
    # Feishu API can return JSON null for merged / unfilled header cells.
    # str(None) = "None" created false duplicate clusters across 52 columns.
    # Accept only text/null; non-text header structures are not trustworthy.
    if any(cell is not None and not isinstance(cell,str) for cell in header):
        raise RuntimeError("HEADER_CELL_NON_TEXT_TYPE")
    normalized = [str(x).strip().casefold() if x is not None else "" for x in header]
    if not any(normalized):
        raise RuntimeError("Empty header")
    seen = {}
    duplicates = []
    for pos, val in enumerate(normalized, start=1):
        if not val:
            continue
        if val in seen:
            duplicates.append((seen[val], pos))
        else:
            seen[val] = pos
    digest = hashlib.sha256(chr(31).join(normalized).encode()).hexdigest()[:16]
    return digest, len(header), duplicates


# The source's row 1 is a merged title/grouping row for these two tabs.
# Read row 2, independently confirmed against the first six raw rows.
PANEL_HEADER_ROW={"Payment Receipt":2,"eTax Invoice":2}
RECEIPT_EXPECTED={
 1:"Deposit Date",2:"Customer Name",3:"Amount (KRW)",4:"CMS No.",
 6:"Date",7:"CMS No.",8:"Amount",
 10:"Date",11:"Customer Name",12:"Amount",13:"CMS No."
}
ETAX_EXPECTED={
 1:"Comments",5:"ERP Invoice Number",10:"Project Number",16:"Amount",
 25:"Comments",26:"Sales",29:"Remark",31:"Paid? Yes ?",
 32:"Status",33:"e-Tax issued?",34:"Remark"
}
def canonical_label(label):
    return " ".join(str(label or "").casefold().split())

def panel_for_position(pos):
    if 1<=pos<=4:return 1
    if 6<=pos<=8:return 2
    if 10<=pos<=13:return 3
    return 0

def validate_panelled_header(fmt,header,duplicates):
    if fmt=="Payment Receipt":
        width,expected=13,RECEIPT_EXPECTED
        # Other panels must never share an ambiguous column. A/B, F/H,
        # J/M are independent amounts, dates and CMS identifiers.
        for first,second in duplicates:
            p1,p2=panel_for_position(first),panel_for_position(second)
            if not p1 or not p2 or p1==p2:
                raise RuntimeError("Duplicate within Receipt panel at "+str(second))
        for gap in (5,9):
            if gap<=len(header) and header[gap-1] is not None and str(header[gap-1]).strip():
                raise RuntimeError("Receipt separator unexpectedly populated at "+str(gap))
    elif fmt=="eTax Invoice":
        width,expected=35,ETAX_EXPECTED
        # The only expected repeated names are Comments and Remark.
        # Any other pair remains blocked pending raw Feishu source review.
        if not set(duplicates).issubset({(1,25),(29,34)}):
            raise RuntimeError("Unapproved duplicate eTax label positions")
    else:
        raise RuntimeError("UNKNOWN_PANELLED_FORMAT")
    if any(cell is not None and str(cell).strip() for cell in header[width:]):
        raise RuntimeError("Additional unapproved panel/header columns")
    for pos,label in expected.items():
        if canonical_label(header[pos-1]) != canonical_label(label):
            raise RuntimeError("Header label mismatch at canonical position "+str(pos))
    return "PASS_PANELLED_RAW_SCHEMA_ONLY"

def validate_header_scope(fmt, header, duplicates):
    """Permit duplicate noncanonical formula tails only after verified core.

    Payment Outstanding core is columns 1-17, Prepayments 1-19. Receipt
    multi-panel and eTax core conflicts must remain blocked for review.
    """
    # Never turn a mostly empty row into PASS after removing spurious null
    # duplicates: all financial core fields must remain visibly populated.
    required = {
        "Payment Outstanding": tuple(range(1,18)),
        "Prepayments": tuple(range(1,20)),
        "Payment Receipt": (1,2,3,4,6,7,8,10,11,12,13),
        "eTax Invoice": tuple(range(1,36))
    }.get(fmt)
    if required is None: raise RuntimeError("UNKNOWN_FEISHU_FORMAT")
    missing = [p for p in required if p>len(header) or
               header[p-1] is None or not str(header[p-1]).strip()]
    if missing:
        raise RuntimeError("Missing canonical header in "+fmt+
                           " column_positions="+",".join(map(str,missing)))
    if fmt in PANEL_HEADER_ROW:
        return validate_panelled_header(fmt,header,duplicates)
    if not duplicates:
        return "PASS"
    core_width = {"Payment Outstanding": 17, "Prepayments": 19}.get(fmt)
    if core_width:
        canonical = [str(x).strip() for x in header[:core_width]]
        if len(canonical) == core_width and all(canonical) and all(
                a > core_width and b > core_width for a, b in duplicates):
            return "REVIEW_NONCANONICAL_TRAILING_DUPLICATES"
    positions = ",".join(str(a)+":"+str(b) for a,b in duplicates)
    raise RuntimeError("Duplicate nonempty header in "+fmt+
                       " duplicate_column_pairs="+positions)


def main():
    print("STAGE: authenticate",flush=True)
    auth=api("/open-apis/auth/v3/tenant_access_token/internal",payload={
        "app_id":os.environ["FEISHU_APP_ID"],"app_secret":os.environ["FEISHU_APP_SECRET"]})
    bearer=auth.get("tenant_access_token")
    if not bearer: raise RuntimeError("AUTH_TOKEN_MISSING")
    root="/open-apis/sheets/v3/spreadsheets/"+urllib.parse.quote(TOKEN,safe="")
    print("STAGE: sheets_list",flush=True)
    sheets=api(root+"/sheets/query",bearer).get("sheets")
    if not isinstance(sheets,list): raise RuntimeError("Sheet listing unavailable")
    selected,unclassified=select(sheets,dt.datetime.now(ZoneInfo("Asia/Seoul")).date())
    if selected is None: raise RuntimeError("Exactly four formats required")
    print("FORMAT_COUNT:",len(selected))
    trailing_reviews=0
    panelled_confirmed=0
    blocked_formats=[]
    for fmt,entry in sorted(selected.items()):
        # A2 is the actual per-column header for Receipt/eTax; A1 contains
        # merged titles and must not be interpreted as column definitions.
        header_row=PANEL_HEADER_ROW.get(fmt,1)
        span=urllib.parse.quote(entry["sheet_id"]+"!A"+str(header_row)+":AZ"+str(header_row),safe="!:")
        value_root="/open-apis/sheets/v2/spreadsheets/"+urllib.parse.quote(TOKEN,safe="")
        print("STAGE: header_read FORMAT:",fmt,flush=True)
        result=api(value_root+"/values/"+span,bearer)
        value_range=result.get("valueRange")
        if not isinstance(value_range,dict): raise RuntimeError("VALUE_RANGE_MISSING")
        values=value_range.get("values") or []
        header=values[0] if values else []
        # Header type counts help distinguish null merged cells from genuine
        # duplicate labels. Only structural counts leave the runner.
        type_counts = {}
        for cell in header:
            key = "NULL" if cell is None else ("TEXT" if isinstance(cell,str) else "OTHER")
            type_counts[key] = type_counts.get(key,0)+1
        print("FORMAT:",fmt,"HEADER_CELL_TYPES:",type_counts)
        try:
            fingerprint,width,duplicates=header_fingerprint(header)
            print("FORMAT:",fmt,"HEADER_COLUMNS:",width,"HEADER_FINGERPRINT:",fingerprint)
            scope=validate_header_scope(fmt,header,duplicates)
        except RuntimeError as exc:
            blocked_formats.append(fmt)
            print("SCHEMA_HEADER_BLOCKED:",fmt,str(exc),flush=True)
            continue
        if scope=="PASS_PANELLED_RAW_SCHEMA_ONLY":
            panelled_confirmed+=1
            print("SCHEMA_HEADER_PANELLED:",fmt,"ROW:",header_row,
                  "VALIDATED_PANELS:",3 if fmt=="Payment Receipt" else 1,
                  "FINANCIAL_VERIFICATION: NOT_PERFORMED")
        elif scope != "PASS":
            trailing_reviews += 1
            core={"Payment Outstanding":17,"Prepayments":19}[fmt]
            print("SCHEMA_HEADER_REVIEW:",fmt,
                  "CANONICAL_COLUMNS: 1-"+str(core)+" UNIQUE_NONEMPTY",
                  "TRAILING_DUPLICATES:",len(duplicates),
                  "FIRST_LAST_DUPLICATE:",duplicates[0],duplicates[-1])
    if blocked_formats:
        print("SCHEMA_AUDIT: REVIEW_REQUIRED")
        print("CELL_CONTENT_LOGGING: DISABLED")
        raise RuntimeError("HEADER_VALIDATION_BLOCKED_FORMATS="+",".join(blocked_formats))
    print("SCHEMA_AUDIT:", "PASS_STRUCTURAL_PANELLED_RAW_HEADER_ONLY" if panelled_confirmed else
           ("PASS_CANONICAL_REVIEW_TRAILING" if trailing_reviews else "PASS"))
    print("CELL_CONTENT_LOGGING: DISABLED")
    print("PAYMENT_CERTIFIED: NO; ETAX_ISSUANCE_CERTIFIED: NO")
    print("BASE_WRITES: 0")
if __name__=="__main__":
    try: main()
    except Exception as exc:
        diagnostic=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
        print("SCHEMA_AUDIT_FAILED:",diagnostic,file=sys.stderr)
        sys.exit(1)
