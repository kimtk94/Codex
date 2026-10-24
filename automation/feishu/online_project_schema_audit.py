#!/usr/bin/env python3
"""Read-only Online-Project schema and aggregate status audit; no customer records logged."""
import collections
import json
import re
import sys
import urllib.parse
from base_readonly_probe import request, require
from payment_table_audit import list_pages

TABLE = "Online-Project"

def main():
    auth = request("POST", "/open-apis/auth/v3/tenant_access_token/internal",
        body={"app_id":require("FEISHU_APP_ID"),"app_secret":require("FEISHU_APP_SECRET")})
    if auth.get("code") != 0 or not auth.get("tenant_access_token"):
        raise RuntimeError("AUTH_FAILED")
    token = auth["tenant_access_token"]
    prefix = "/open-apis/bitable/v1/apps/" + urllib.parse.quote(require("FEISHU_BASE_APP_TOKEN"),safe="")
    tables = list(list_pages(prefix+"/tables",token))
    matched = [t for t in tables if t.get("name")==TABLE]
    if len(matched)!=1: raise RuntimeError("TARGET_NOT_UNIQUE")
    root=prefix+"/tables/"+urllib.parse.quote(matched[0]["table_id"],safe="")
    fields=list(list_pages(root+"/fields",token))
    records=list(list_pages(root+"/records",token))
    print("ONLINE_PROJECT_RECORDS:",len(records))
    for f in fields:
        name=str(f.get("field_name",""))
        # Schema field names are metadata; no customer values.
        print("FIELD_SCHEMA:",json.dumps({"name":name,"type":f.get("type")},ensure_ascii=False))
    for f in fields:
        name=str(f.get("field_name",""))
        if not re.search(r"status|stage|progress|step|workflow|process|状态|进度|단계|진행",name,re.I):
            continue
        values=collections.Counter()
        for rec in records:
            val=(rec.get("fields") or {}).get(name)
            if isinstance(val,(list,dict)):
                val="COMPLEX"
            text=str(val or "").strip()
            if len(text)>80 or re.search(r"@|\\d{6,}",text):text="REDACTED"
            values[text or "(empty)"]+=1
        print("STATUS_DISTRIBUTION:",json.dumps({"field":name,"counts":values.most_common(30)},ensure_ascii=False))
    print("SOURCE_WRITES: 0")
if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("SCHEMA_AUDIT_FAILED:",type(exc).__name__,file=sys.stderr)
        sys.exit(1)
