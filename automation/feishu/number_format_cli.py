#!/usr/bin/env python3
"""Render integer Feishu count columns without trailing .0.

Never changes source values or column types. Full-definition update is used
only after reading and validating each numeric field's current configuration.
"""
import json
import os
import sys
from native_dashboard_cli import BASE,cli

COUNTS=(
    ("Weekly Quote KPI","Approved Quote Count"),
    ("Weekly Quote KPI","Created In Week Count"),
    ("Weekly Quote KPI","Verified Amount Quote Count"),
    ("Weekly Quote KPI","Unmatched Amount Count"),
    ("Monthly Tax Invoice","Invoice Count"),
    ("Monthly Tax Invoice","CSS Source Invoice Count"),
)

def read_field(table,name):
    result=cli("+field-get","--base-token",BASE,
               "--table-id",table,"--field-id",name)
    candidate=result.get("field") if isinstance(result,dict) else None
    if not isinstance(candidate,dict):
        raise RuntimeError("NUMBER_FIELD_SCHEMA_UNKNOWN")
    if candidate.get("name")!=name or candidate.get("type")!="number":
        raise RuntimeError("NUMBER_FIELD_TYPE_OR_NAME_MISMATCH")
    style=candidate.get("style") or {"type":"plain"}
    if not isinstance(style,dict) or style.get("type","plain")!="plain":
        raise RuntimeError("NUMBER_FIELD_NONPLAIN_STYLE")
    if style.get("percentage") not in (None,False):
        raise RuntimeError("NUMBER_FIELD_PERCENTAGE_NOT_ALLOWED")
    return candidate

def payload(current):
    style=dict(current.get("style") or {})
    if style.get("type","plain")!="plain":
        raise ValueError("NONPLAIN_NUMBER")
    style["type"]="plain"
    style["precision"]=0
    # Only supported writable definition fields. Never send computed/id flags.
    body={"name":current["name"],"type":"number","style":style}
    for key in ("description","default_value"):
        if key in current and current[key] is not None:
            body[key]=current[key]
    return body

def main():
    if os.environ.get("FEISHU_BASE_APP_TOKEN")!=BASE:
        raise RuntimeError("REFUSE_OTHER_BASE")
    mode=os.environ.get("FEISHU_NUMBER_FORMAT_MODE","plan")
    if mode not in {"plan","apply"}:
        raise RuntimeError("INVALID_NUMBER_MODE")
    targets=[(table,name,read_field(table,name)) for table,name in COUNTS]
    if mode=="plan":
        print("FEISHU_NUMBER_FORMAT_PLAN_PASS count_fields="+str(len(targets))+
              " writes=0")
        return
    updated=0
    for table,name,original in targets:
        if (original.get("style") or {}).get("precision")==0:
            continue
        # The CLI command is a full overwrite: preserve pre-existing writable
        # style attributes and optional description/default_value.
        body=payload(original)
        cli("+field-update","--base-token",BASE,
            "--table-id",table,"--field-id",name,
            "--json",json.dumps(body,ensure_ascii=False,separators=(",",":")),
            "--yes")
        check=read_field(table,name)
        if (check.get("style") or {}).get("precision")!=0:
            raise RuntimeError("FEISHU_NUMBER_FORMAT_READBACK_FAILED")
        updated+=1
        print("FEISHU_INTEGER_COUNT_PRECISION_SET table="+table+" field="+name)
    print("FEISHU_INTEGER_FORMAT_PASS targets="+str(len(targets))+
          " updated="+str(updated)+" source_values_changed=0")

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("FEISHU_NUMBER_FORMAT_FAILED="+(
            str(e) if isinstance(e,(RuntimeError,ValueError)) else type(e).__name__),
            file=sys.stderr)
        sys.exit(1)
