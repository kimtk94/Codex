#!/usr/bin/env python3
"""Per-Quote review policy: full list, strict ACTIVE gate, manual opt-out.

Feishu owns the "합산 제외" checkbox; SFDC/QQ source owns all other fields.
Do not infer active from an approval alone. Unknown is NOT included.
"""
import collections
import datetime as dt
import re

from qq_mail_ingest import SafeError, api, list_all, plain_field
from quote_process_amount import sf15, quote_id, week_for

TABLE="Weekly Quote Review"
CHECKBOX="합산 제외"
INCLUDED="INCLUDED"
NOT_INCLUDED="NOT_INCLUDED"
SCHEMA=[
    ("Quote Name",1),  # Primary column for human-friendly native grid
    ("Source Key",1),
    ("Week Start",1),
    ("Approval KST",1),
    ("SFDC Record ID",1),
    ("Quote Status",1),
    ("Approved AND Active",1),
    ("SFDC IsActive",1),
    (CHECKBOX,7),
    ("합산 상태",1),
    ("제외 이유",1),
    ("Last Sync KST",1),
]
VIEW_SPECS=(
    ("전체 Quote 목록",None,None),
    ("합산 대상 Quote","합산 상태",INCLUDED),
    ("합산 제외 · 미확인","합산 상태",NOT_INCLUDED),
)


def cell(row,key):
    return str(row.get(key) or "").strip()


def checkbox(value):
    """Feishu reads checkbox as JSON bool; do not turn ambiguous text into yes."""
    if isinstance(value,bool):
        return value
    if isinstance(value,list) and len(value)==1:
        return checkbox(value[0])
    return value in ("true","TRUE","1",1)


def read_overrides(records):
    result={}
    for rec in records:
        fields=rec.get("fields") or {}
        key=plain_field(fields.get("Source Key")).strip()
        if not key:
            continue
        if key in result:
            raise SafeError("WEEKLY_REVIEW_DUPLICATE_SOURCE_KEY")
        if not key.startswith("QUOTE_REVIEW:a0P"):
            raise SafeError("WEEKLY_REVIEW_UNEXPECTED_SOURCE_KEY")
        result[key]=checkbox(fields.get(CHECKBOX))
    return result


def review_rows(source,overrides=None):
    """List every canonical approval by immutable Quote ID even if inactive."""
    overrides=overrides or {}
    approval=source.get("Quote Approval Dedup",[])
    exported={}
    for row in source.get("SFDC Quote Export",[]):
        sid=sf15(cell(row,"Salesforce Record ID"))
        if not sid:
            raise SafeError("WEEKLY_REVIEW_INVALID_EXPORT_ID")
        if sid in exported:
            raise SafeError("WEEKLY_REVIEW_DUPLICATE_EXPORT_ID")
        exported[sid]=cell(row,"IsActive").lower()
    output={}
    for row in approval:
        sid=sf15(cell(row,"SFDC Record ID"))
        week=week_for(cell(row,"Approval KST"))
        if not sid or not sid.startswith("a0P") or not week:
            raise SafeError("WEEKLY_REVIEW_INVALID_APPROVAL_ID_OR_WEEK")
        key="QUOTE_REVIEW:"+sid
        if key in output:
            raise SafeError("WEEKLY_REVIEW_DUPLICATE_APPROVAL_ID")
        status=cell(row,"Quote Status").upper()
        approved=cell(row,"Approved AND Active").upper()
        is_active=exported.get(sid,"")
        manual=bool(overrides.get(key,False))
        if manual:
            reason="MANUAL_EXCLUDED"
        elif status=="INACTIVE" or approved=="NO" or is_active in ("0","false"):
            reason="NOT_ACTIVE"
        elif status=="ACTIVE" and approved=="YES" and is_active in ("1","true"):
            reason=""
        else:
            reason="ACTIVE_NOT_VERIFIED"
        output[key]={
            "Source Key":key,
            "Week Start":week,
            "Approval KST":cell(row,"Approval KST"),
            "Quote Name":cell(row,"Quotation Name"),
            "SFDC Record ID":sid,
            "Quote Status":status or "UNKNOWN",
            "Approved AND Active":approved or "UNVERIFIED",
            "SFDC IsActive":is_active or "UNVERIFIED",
            "합산 상태":NOT_INCLUDED if reason else INCLUDED,
            "제외 이유":reason,
        }
    print("QUOTE_REVIEW_SOURCE_PASS total="+str(len(output))
          +" included="+str(sum(r["합산 상태"]==INCLUDED for r in output.values()))
          +" excluded="+str(sum(r["합산 상태"]==NOT_INCLUDED for r in output.values()))
          +" manual="+str(sum(bool(overrides.get(k,False)) for k in output)))
    return list(output.values())


def membership(rows):
    """Guard duplicate week+ID; include only explicit ACTIVE and unexcluded."""
    approved=collections.defaultdict(set)
    included=collections.defaultdict(set)
    for row in rows:
        week=row["Week Start"]
        sid=row["SFDC Record ID"]
        if sid in approved[week]:
            raise SafeError("WEEKLY_REVIEW_DUPLICATE_WEEK_MEMBER")
        approved[week].add(sid)
        if row["합산 상태"]==INCLUDED:
            included[week].add(sid)
    return approved,included


def equal_source(before,row):
    for name,value in row.items():
        observed=before.get(name)
        if plain_field(observed).strip()!=str(value).strip():
            return False
    return True


def sync_review(token,path,desired,existing,now):
    """Batch source-owned writes only: keep user checkbox in all updates."""
    indexed={}
    for record in existing:
        fields=record.get("fields") or {}
        key=plain_field(fields.get("Source Key")).strip()
        if not key or key in indexed:
            raise SafeError("WEEKLY_REVIEW_INVALID_OR_DUPLICATE_RECORD")
        indexed[key]=record
    creates=[]; updates=[]; unchanged=0
    for row in desired:
        key=row["Source Key"]
        old=indexed.get(key)
        fields=(old.get("fields") or {}) if old else {}
        if old and equal_source(fields,row):
            unchanged+=1
            continue
        patch={**row,"Last Sync KST":now}
        if old:
            updates.append({"record_id":old["record_id"],"fields":patch})
        else:
            # Checkbox defaults to false only on insert; subsequent syncs
            # never send this user-owned field (including false).
            creates.append({"fields":{**patch,CHECKBOX:False}})
    for action,items in (("batch_create",creates),("batch_update",updates)):
        for start in range(0,len(items),25):
            chunk=items[start:start+25]
            resp=api("POST",path+"/records/"+action,token,
                     data={"records":chunk},action="weekly_review_"+action)
            if len(resp.get("records") or [])!=len(chunk):
                raise SafeError("WEEKLY_REVIEW_BATCH_WRITE_UNVERIFIED")
    after=list_all(path+"/records",token,"weekly_review_readback")
    found={}
    for rec in after:
        key=plain_field((rec.get("fields") or {}).get("Source Key")).strip()
        if not key or key in found:
            raise SafeError("WEEKLY_REVIEW_READBACK_DUPLICATE")
        found[key]=rec.get("fields") or {}
    for row in desired:
        key=row["Source Key"]
        if key not in found or not equal_source(found[key],row):
            raise SafeError("WEEKLY_REVIEW_READBACK_MISMATCH")
    prior_flags=read_overrides(existing)
    result_flags=read_overrides(after)
    for key in set(prior_flags)&set(result_flags):
        if prior_flags[key]!=result_flags[key]:
            raise SafeError("WEEKLY_REVIEW_MANUAL_OVERRIDE_LOST")
    print("WEEKLY_REVIEW_SYNC_PASS desired="+str(len(desired))
          +" created="+str(len(creates))+" updated="+str(len(updates))
          +" unchanged="+str(unchanged)+" manual_preserved=PASS")
    return result_flags
