#!/usr/bin/env python3
"""Read-only discovery of rotating eTAX invoice tables in Feishu Base."""
import re
import sys
import urllib.parse
from base_readonly_probe import request, require
from payment_table_audit import list_pages

MONTHS = {m:i for i,m in enumerate(("jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"),1)}

def parse_etax_month(name, reference_year):
    """Identify unissued eTAX invoice monthly table names; reject ambiguous names."""
    s = " ".join(str(name or "").strip().lower().split())
    if not re.search(r"\be[\s_-]*tax\b", s) or not re.search(r"\binvoices?\b", s):
        return None
    matches = [(int(n), m.start()) for m in re.finditer(r"(?<!\d)(0?[1-9]|1[0-2])(?=[./ _-])", s) for n in [m.group(1)]]
    word_months = [i for k,i in MONTHS.items() if re.search(r"\b"+k+r"[a-z]*\b", s)]
    if len(set(word_months)) == 1:
        month = word_months[0]
    elif len(set(word_months)) > 1:
        return None
    else:
        # Numeric month only when explicitly in YYYY-MM or MM-YYYY form.
        ym = re.search(r"\b(20\d\d)[-/._ ](0?[1-9]|1[0-2])\b",s)
        my = re.search(r"\b(0?[1-9]|1[0-2])[-/._ ](20\d\d)\b",s)
        if ym: return int(ym.group(1)), int(ym.group(2))
        if my: return int(my.group(2)), int(my.group(1))
        return None
    years = [int(y) for y in re.findall(r"(?<!\d)20\d\d(?!\d)",s)]
    if len(set(years))>1: return None
    return (years[0] if years else reference_year), month

def select_etax(tables, year, month):
    matches=[t for t in tables if parse_etax_month(t.get("name"),year)==(year,month)]
    if len(matches)!=1:
        return None,len(matches)
    return matches[0],1

def main():
    from datetime import datetime, timezone, timedelta
    today=datetime.now(timezone(timedelta(hours=9)))
    auth=request("POST","/open-apis/auth/v3/tenant_access_token/internal",
      body={"app_id":require("FEISHU_APP_ID"),"app_secret":require("FEISHU_APP_SECRET")})
    if auth.get("code")!=0 or not auth.get("tenant_access_token"): raise RuntimeError("AUTH_REJECTED")
    token=auth["tenant_access_token"]
    prefix="/open-apis/bitable/v1/apps/"+urllib.parse.quote(require("FEISHU_BASE_APP_TOKEN"),safe="")
    tables=list(list_pages(prefix+"/tables",token))
    selected,count=select_etax(tables,today.year,today.month)
    print("ETAX_TARGET_MONTH:",today.strftime("%Y-%m"))
    print("ETAX_MATCHING_TABLE_COUNT:",count)
    if not selected:
        print("ETAX_SOURCE_STATUS: BLOCKED_MISSING_OR_AMBIGUOUS")
        return 2
    root=prefix+"/tables/"+urllib.parse.quote(selected["table_id"],safe="")
    fields=list(list_pages(root+"/fields",token))
    records=list(list_pages(root+"/records",token))
    if any(not r.get("record_id") for r in records): raise RuntimeError("RECORD_ID_MISSING")
    print("ETAX_SOURCE_STATUS: FOUND")
    print("ETAX_FIELD_COUNT:",len(fields))
    print("ETAX_UNISSUED_RECORD_COUNT:",len(records))
    print("ETAX_WRITE_OPERATIONS: 0")
    return 0

if __name__=="__main__":
    try: sys.exit(main())
    except Exception as e:
        print("ETAX_DISCOVERY_FAILED:",type(e).__name__,file=sys.stderr)
        sys.exit(1)
