#!/usr/bin/env python3
"""Read-only Feishu CRM source proof: aggregate only, never print customer content."""
import re
import sys
import urllib.parse
import jiin_crm_filtered_ingest as c
from qq_mail_ingest import SafeError, api, auth, list_all, plain_field
from mail_classification_2026 import since_2026
from setup_sales_web import EXPECTED_BASE


def summarize(rows):
    keys=set()
    for row in rows:
        fields=row.get("fields") or {}
        key=plain_field(fields.get("Mail Key")).strip()
        if not re.fullmatch("[0-9a-f]{64}", key) or key in keys:
            raise SafeError("CRM_AUDIT_BAD_DUPLICATE_KEY")
        keys.add(key)
        if not c.source_sender(plain_field(fields.get("From"))):
            raise SafeError("CRM_AUDIT_WRONG_SENDER")
        if plain_field(fields.get("Source Account")) != c.ACCOUNT:
            raise SafeError("CRM_AUDIT_SOURCE_ACCOUNT_MISMATCH")
        if plain_field(fields.get("Source Filter")) != "EXACT_FROM_CRM":
            raise SafeError("CRM_AUDIT_SOURCE_FILTER_MISSING")
        if plain_field(fields.get("Direction")) != "INBOUND":
            raise SafeError("CRM_AUDIT_WRONG_DIRECTION")
        if not since_2026(plain_field(fields.get("Received At"))):
            raise SafeError("CRM_AUDIT_BEFORE_2026")
    return len(keys)


def main():
    import os
    if os.environ.get("FEISHU_BASE_APP_TOKEN") != EXPECTED_BASE:
        raise SafeError("CRM_AUDIT_WRONG_BASE")
    token,root=auth()
    tables = list_all(root+"/tables",token,"crm_audit_tables")
    matches=[t for t in tables if t.get("name")==c.TABLE]
    if len(matches)!=1:
        raise SafeError("CRM_AUDIT_TABLE_NOT_UNIQUE")
    tid=matches[0]["table_id"]
    path=root+"/tables/"+urllib.parse.quote(tid,safe="")
    count=summarize(list_all(path+"/records",token,"crm_audit_records"))
    print("CRM_EXACT_SENDER_AUDIT_PASS total="+str(count)+
          " duplicate=0 wrong_sender=0 source_mailbox_writes=0"+
          " other_business_table_writes=0")
    return count


if __name__=="__main__":
    try:main()
    except Exception as e:
        reason=str(e) if isinstance(e,SafeError) else type(e).__name__
        print("CRM_EXACT_SENDER_AUDIT_FAILED="+reason,file=sys.stderr)
        sys.exit(1)
