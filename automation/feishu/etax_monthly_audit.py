#!/usr/bin/env python3
"""Read-only discovery of rotating eTAX invoice tables in Feishu Base."""
import re
import sys
import urllib.parse
from base_readonly_probe import request, require
from payment_table_audit import list_pages, TARGET as OUTSTANDING_TABLE

MONTHS = {m:i for i,m in enumerate(("jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"),1)}

def parse_etax_month(name, reference_year):
    """Identify unissued eTAX invoice monthly table names; reject ambiguous names."""
    s = " ".join(str(name or "").strip().lower().split())
    if not re.search(r"\be[\s_-]*tax\b", s) or not re.search(r"\binvoices?\b", s):
        return None
    word_months = [i for k,i in MONTHS.items() if re.search(r"\b"+k+r"[a-z]*\b", s)]
    if len(set(word_months)) == 1:
        month = word_months[0]
        # Do not infer a month if another explicit numeric YYYY-MM disagrees.
        numeric = re.search(r"\b(20\d\d)[-/._ ](0?[1-9]|1[0-2])\b", s)
        if numeric and int(numeric.group(2)) != month: return None
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
    outstanding=[t for t in tables if t.get("name")==OUTSTANDING_TABLE]
    if len(outstanding)!=1:
        print("ETAX_OUTSTANDING_OVERLAP: UNVERIFIED_OUTSTANDING_SOURCE")
    else:
        pay_root=prefix+"/tables/"+urllib.parse.quote(outstanding[0]["table_id"],safe="")
        pf=list(list_pages(pay_root+"/fields",token))
        pr=list(list_pages(pay_root+"/records",token))
        aliases={"project id","amea project id","project number","project no"}
        def keyname(fs):
            found=[f.get("field_name") for f in fs if str(f.get("field_name") or "").lower().strip().replace("_"," ") in aliases]
            return found[0] if len(found)==1 else None
        ek,pk=keyname(fields),keyname(pf)
        if not ek or not pk:
            print("ETAX_OUTSTANDING_OVERLAP: UNVERIFIED_PROJECT_ID_SCHEMA")
        else:
            def ids(rows,key):
                out=set()
                for r in rows:
                    value=(r.get("fields") or {}).get(key)
                    if isinstance(value,str):
                        v=re.sub(r"[^A-Z0-9]","",value.upper())
                        if v: out.add(v)
                return out
            a,b=ids(records,ek),ids(pr,pk)
            if not a or not b:
                print("ETAX_OUTSTANDING_OVERLAP: UNVERIFIED_IDS")
            else:
                print("ETAX_OUTSTANDING_OVERLAP: VERIFIED")
                print("ETAX_OUTSTANDING_OVERLAP_PROJECT_COUNT:",len(a&b))
                print("ETAX_ONLY_PROJECT_COUNT:",len(a-b))
                print("OUTSTANDING_ONLY_PROJECT_COUNT:",len(b-a))
    print("ETAX_WRITE_OPERATIONS: 0")
    return 0

if __name__=="__main__":
    try: sys.exit(main())
    except Exception as e:
        print("ETAX_DISCOVERY_FAILED:",type(e).__name__,file=sys.stderr)
        sys.exit(1)
