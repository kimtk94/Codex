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
    blocked_formats=[]
    for fmt,entry in sorted(selected.items()):
        # A1:AZ1 is header-only; structural fingerprints do not disclose names.
        span=urllib.parse.quote(entry["sheet_id"]+"!A1:AZ1",safe="!:")
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
        if scope != "PASS":
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
    print("SCHEMA_AUDIT:", "PASS_CANONICAL_REVIEW_TRAILING" if trailing_reviews else "PASS")
    print("CELL_CONTENT_LOGGING: DISABLED")
    print("BASE_WRITES: 0")
if __name__=="__main__":
    try: main()
    except Exception as exc:
        diagnostic=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
        print("SCHEMA_AUDIT_FAILED:",diagnostic,file=sys.stderr)
        sys.exit(1)
