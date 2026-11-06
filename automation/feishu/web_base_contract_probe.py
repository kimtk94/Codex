#!/usr/bin/env python3
"""Read-only Feishu Sales Base web-source contract; logs no customer records."""
import os
import sys
import urllib.parse
from qq_mail_ingest import auth, list_all, SafeError

BASE="IpMkbUD0vaFqtYs93a3csXtdn1b"
TABLE="tblTZe5tkRUeOHM8"
REQUIRED={"Source Key","AMEA","Quote Full Name","Quote Match State",
          "Current Stage","Progress %","Prepayment","SIF State",
          "PO Evidence","Next Action","Institution","Customer","Service"}

def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != BASE:
        raise SafeError("WRONG_FEISHU_SALES_BASE")
    token,root=auth()
    path=root+"/tables/"+urllib.parse.quote(TABLE,safe="")
    fields=list_all(path+"/fields",token,"web_base_fields")
    names={x.get("field_name") for x in fields}
    missing=REQUIRED-names
    if missing:
        raise SafeError("WEB_BASE_SCHEMA_MISSING_"+str(len(missing)))
    rows=list_all(path+"/records",token,"web_base_records")
    if not rows:
        raise SafeError("WEB_BASE_EMPTY")
    keys=set()
    for row in rows:
        key=(row.get("fields") or {}).get("Source Key")
        if isinstance(key,list):
            key="".join(v.get("text","") for v in key if isinstance(v,dict))
        key=str(key or "").strip()
        if not key or key in keys:
            raise SafeError("WEB_BASE_DUPLICATE_OR_EMPTY_SOURCE_KEY")
        keys.add(key)
    print("FEISHU_WEB_BASE_CONTRACT_PASS rows="+str(len(rows))+
          " fields="+str(len(REQUIRED))+" writes=0 customer_payload_logged=0")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("FEISHU_WEB_BASE_CONTRACT_FAILED:"+
              (str(exc) if isinstance(exc,SafeError) else type(exc).__name__),file=sys.stderr)
        sys.exit(1)
