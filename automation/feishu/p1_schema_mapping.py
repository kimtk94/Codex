#!/usr/bin/env python3
"""P1 read-only structural audit; no personal values printed and no writes."""
import collections
import json
import os
import sys
import urllib.parse
from multisource_dryrun import get_json, pages, TABLE, VIEW

ALIASES = {
    "record_id": ["record_id", "salesforce_id", "sfdc_id"],
    "institution": ["institution", "account", "기관"],
    "customer_name": ["customer_name", "name", "고객명"],
    "email": ["email", "customer_email", "이메일"],
    "service": ["service", "service_category", "서비스"],
    "status": ["status", "current_status", "진행상태"],
    "latest_event": ["latest_event_at", "received_at", "최근활동"],
}
def normal(s):
    return "".join(c for c in str(s or "").casefold() if c.isalnum())
def main():
    for name in ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_BASE_APP_TOKEN"):
        if not os.environ.get(name):
            raise RuntimeError("Missing "+name)
    auth=get_json("/open-apis/auth/v3/tenant_access_token/internal",
        data={"app_id":os.environ["FEISHU_APP_ID"],"app_secret":os.environ["FEISHU_APP_SECRET"]})
    token=auth["tenant_access_token"]
    prefix="/open-apis/bitable/v1/apps/"+urllib.parse.quote(os.environ["FEISHU_BASE_APP_TOKEN"],safe="")+"/tables/"+TABLE
    fields=list(pages(prefix+"/fields",token))
    views=list(pages(prefix+"/views",token))
    if not any(v.get("view_id")==VIEW and v.get("view_name")=="Taehoon" for v in views):
        raise RuntimeError("View mismatch")
    names=collections.Counter(normal(f.get("field_name")) for f in fields)
    print("FIELD_COUNT:",len(fields))
    print("FIELD_MAPPING_CANDIDATES:",json.dumps({
        role:sum(names[normal(a)] for a in aliases) for role,aliases in ALIASES.items()
    },sort_keys=True))
    print("SOURCE_SFDC: SCHEMA_NOT_YET_CONNECTED")
    print("SOURCE_MAIL: SCHEMA_NOT_YET_CONNECTED")
    print("WRITE_ACCESS: NOT_TESTED")
    print("WRITE_OPERATIONS: 0")
    print("P1_SCHEMA_AUDIT: PASS")
if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print("P1_FAILED:",type(exc).__name__,file=sys.stderr)
        sys.exit(1)
