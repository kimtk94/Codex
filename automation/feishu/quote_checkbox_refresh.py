#!/usr/bin/env python3
"""Read Feishu's user-owned checkbox, then reaggregate only on actual changes.

This does not poll QQ mail or edit the checkbox. Source validation happens in
sales_metrics_sync.main before it writes the Quote KPI. All other tables
(Payment, Monthly, etc.) remain untouched.
"""
import os
import sys
from qq_mail_ingest import SafeError, auth, list_all, plain_field
from weekly_quote_review import CHECKBOX, checkbox
import sales_metrics_sync as metrics

def pending_manual_changes(rows):
    seen=set()
    changed=[]
    for item in rows:
        fields=item.get("fields") or {}
        key=plain_field(fields.get("Source Key")).strip()
        if not key.startswith("QUOTE_REVIEW:a0P") or key in seen:
            raise SafeError("QUOTE_CHECKBOX_BAD_OR_DUPLICATE_SOURCE_KEY")
        seen.add(key)
        checked=checkbox(fields.get(CHECKBOX))
        reason=plain_field(fields.get("제외 이유")).strip()
        if (checked and reason!="MANUAL_EXCLUDED") or (
            not checked and reason=="MANUAL_EXCLUDED"
        ):
            changed.append(key)
    if not seen:
        raise SafeError("QUOTE_CHECKBOX_NO_REVIEW_ROWS")
    return changed

def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=metrics.EXPECTED_BASE:
        raise SafeError("QUOTE_CHECKBOX_UNKNOWN_BASE")
    token,root=auth()
    catalog=metrics.table_catalog(token,root)
    ids=catalog.get(metrics.QUOTE_REVIEW_TABLE,[])
    if len(ids)!=1:
        raise SafeError("QUOTE_CHECKBOX_REVIEW_TABLE_NOT_UNIQUE")
    path=metrics.table_path(root,ids[0])
    existing=list_all(path+"/records",token,"quote_checkbox_scan")
    changed=pending_manual_changes(existing)
    if not changed:
        print("QUOTE_CHECKBOX_NO_CHANGE_PASS checked="+str(len(existing))+
              " source_writes=0 sink_writes=0",flush=True)
        return
    print("QUOTE_CHECKBOX_CHANGES_DETECTED count="+str(len(changed))+
          " next=source_validate_and_quote_only",flush=True)
    metrics.main()
    print("QUOTE_CHECKBOX_REFRESH_PASS changed="+str(len(changed))+
          " manual_checkbox_writes=0 payment_monthly_writes=0",flush=True)

if __name__=="__main__":
    try:
        main()
    except Exception as e:
        print("QUOTE_CHECKBOX_REFRESH_FAILED="+(
            str(e) if isinstance(e,SafeError) else type(e).__name__),file=sys.stderr)
        raise SystemExit(1)
