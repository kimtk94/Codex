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
    normalized = [str(x).strip().casefold() for x in header]
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
    """Only Payment Outstanding's first 17 columns are canonical.

    Formula-derived tail headers may be repeated, but never permit duplicate
    business headers, missing canonical columns or duplicates in other formats.
    """
    if not duplicates:
        return "PASS"
    if fmt == "Payment Outstanding":
        canonical = [str(x).strip() for x in header[:17]]
        if len(canonical) == 17 and all(canonical) and all(a > 17 and b > 17
                                                         for a, b in duplicates):
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
        fingerprint, width, duplicates=header_fingerprint(header)
        print("FORMAT:",fmt,"HEADER_COLUMNS:",width,"HEADER_FINGERPRINT:",fingerprint)
        scope=validate_header_scope(fmt,header,duplicates)
        if scope != "PASS":
            trailing_reviews += 1
            print("SCHEMA_HEADER_REVIEW:",fmt,
                  "CANONICAL_COLUMNS: 1-17 UNIQUE_NONEMPTY",
                  "TRAILING_DUPLICATES:",len(duplicates),
                  "FIRST_LAST_DUPLICATE:",duplicates[0],duplicates[-1])
    print("SCHEMA_AUDIT:", "PASS_CANONICAL_REVIEW_TRAILING" if trailing_reviews else "PASS")
    print("CELL_CONTENT_LOGGING: DISABLED")
    print("BASE_WRITES: 0")
if __name__=="__main__":
    try: main()
    except Exception as exc:
        diagnostic=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
        print("SCHEMA_AUDIT_FAILED:",diagnostic,file=sys.stderr)
        sys.exit(1)
