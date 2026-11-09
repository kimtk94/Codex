#!/usr/bin/env python3
"""Per-Quote review policy: full list, strict ACTIVE gate, manual opt-out.

Feishu owns the "합산 제외" checkbox; SFDC/QQ source owns all other fields.
Do not infer active from an approval alone. Unknown is NOT included.
"""
import collections
import datetime as dt
import re

from qq_mail_ingest import SafeError, api, list_all, plain_field
from quote_process_amount import (
    sf15, quote_id, week_for, validate_source, source_fresh, KST, weekly_calculations,
)

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
    ("Active Evidence Source",1),
    ("Active Evidence KST",1),
    ("Chart Window",1), ("기관",1), ("Opportunity",1),
    ("서비스·공정",1), ("샘플수(공정별)",1),
    ("참고 금액 K USD",2), ("참고 견적 USD",1), ("금액 근거",1),
    (CHECKBOX,7),
    ("합산 상태",1),
    ("제외 이유",1),
    ("Last Sync KST",1),
]
VIEW_SPECS=(
    ("그래프 연동 · 최근 5주 검토","Chart Window","RECENT_4_PLUS_CURRENT"),
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


def chart_window_weeks(source,now):
    """Mirror Weekly KPI's 4 closed Friday weeks + 1 ongoing week."""
    valid={}
    for entry in source.get("SFDC Weekly Overview",[]):
        week=cell(entry,"week_start")
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",week):
            continue
        try:
            date=dt.date.fromisoformat(week)
        except ValueError:
            continue
        if date.weekday()!=4:
            continue
        if week in valid:
            raise SafeError("WEEKLY_REVIEW_DUPLICATE_WEEK")
        valid[week]="IN_PROGRESS" in cell(entry,"weekly_basis").upper()
    if valid:
        closed=sorted((w for w,p in valid.items() if not p),reverse=True)[:4]
        running=sorted((w for w,p in valid.items() if p),reverse=True)[:1]
        return set(closed+running)
    # Unit fixtures without a weekly overview still get a safe 5-week scope;
    # production report weeks always follow the verified KPI overview.
    today=dt.date.fromisoformat(week_for(now.date().isoformat()))
    return {(today-dt.timedelta(days=7*n)).isoformat() for n in range(5)}


def quote_detail(rows):
    """Use the latest authenticated QQ Report for decision context only."""
    if not rows:
        return {"기관":"","Opportunity":"","서비스·공정":"",
                "샘플수(공정별)":""}
    account={cell(r,"Account Name: Account Name") for r in rows}
    opportunity={cell(r,"Opportunity Name: Opportunity Name") for r in rows}
    services=sorted({cell(r,"Quote Process Name") or
                     cell(r,"Quotation Process Name") for r in rows} - {""})
    quantity=sorted({cell(r,"Sample Quantity") for r in rows} - {""})
    return {
        "기관":next(iter(account)) if len(account)==1 else "원본 불일치·검토",
        "Opportunity":next(iter(opportunity)) if len(opportunity)==1 else "원본 불일치·검토",
        "서비스·공정":" / ".join(services),
        "샘플수(공정별)":" / ".join(quantity),
    }


def review_rows(source,overrides=None,now=None):
    """Review ALL approvals using authenticated, timely SFDC Quote Active proof.

    Preferred: 17:00 authenticated QQ Quotation report with process-row Active
    uniformly 1 or 0 for an exact immutable QID.
    Fallback: timely direct Salesforce Quote Export with independently matched
    Quote Status. A stale October export must NEVER turn a November unknown
    quote into 0/Inactive. Manual exclusions always take precedence.
    """
    overrides=overrides or {}
    now=now or dt.datetime.now(KST)
    approval=source.get("Quote Approval Dedup",[])
    state=validate_source(source,now)
    verified_mail=state=="SOURCE_QQ_REPORT_VERIFIED"
    source_stamps=[cell(r,"Source Received KST")
                   for r in source.get("SFDC Email Ingest Audit",[])
                   if cell(r,"Entity")=="Quotation"]
    receipt=source_stamps[0] if len(source_stamps)==1 else ""
    raw_states=collections.defaultdict(set)
    detail_by_qid=collections.defaultdict(list)
    if verified_mail:
        for row in source["SFDC Email Quotation Raw"]:
            qid=quote_id(cell(row,"SFDC Quotation ID"))
            if qid:
                raw_states[qid].add(cell(row,"Active").lower())
                detail_by_qid[qid].append(row)
    amounts_by_week,amount_info=weekly_calculations(source,now)
    amount_by_sid={sid:amount
                   for week in amounts_by_week.values()
                   for sid,amount in week["amount_by_sid"].items()}
    if amount_info["source_state"]!="SOURCE_QQ_REPORT_VERIFIED":
        amount_by_sid={}
    shown_weeks=chart_window_weeks(source,now)
    exported={}
    for row in source.get("SFDC Quote Export",[]):
        sid=sf15(cell(row,"Salesforce Record ID"))
        if not sid:
            raise SafeError("WEEKLY_REVIEW_INVALID_EXPORT_ID")
        if sid in exported:
            raise SafeError("WEEKLY_REVIEW_DUPLICATE_EXPORT_ID")
        exported[sid]=row
    output={}
    for row in approval:
        sid=sf15(cell(row,"SFDC Record ID"))
        week=week_for(cell(row,"Approval KST"))
        if not sid or not sid.startswith("a0P") or not week:
            raise SafeError("WEEKLY_REVIEW_INVALID_APPROVAL_ID_OR_WEEK")
        key="QUOTE_REVIEW:"+sid
        if key in output:
            raise SafeError("WEEKLY_REVIEW_DUPLICATE_APPROVAL_ID")
        qid=quote_id(cell(row,"Quotation Name"))
        # An unparseable QID remains visible, but cannot prove Active.
        # Never infer its identity or delete the approved-list entry.
        raw_flag=raw_states.get(qid,set()) if verified_mail and qid else set()
        evidence_source=""
        evidence_when=""
        if verified_mail:
            # An ambiguous/missing QID or contradictory Active rows is NO_VALUE.
            flag=next(iter(raw_flag)) if len(raw_flag)==1 else ""
            flag=flag if flag in ("0","1") else ""
            if flag:
                evidence_source="QQ_3REPORT_VERIFIED"
                evidence_when=receipt
        else:
            old=exported.get(sid,{})
            flag=cell(old,"IsActive").lower()
            fresh=source_fresh(cell(old,"Exported At KST"),now)
            status=cell(row,"Quote Status").upper()
            approved=cell(row,"Approved AND Active").upper()
            # Missing/inconsistent historical snapshot cannot prove Active.
            consistent=(flag=="1" and status=="ACTIVE" and approved=="YES") or (
                        flag=="0" and status=="INACTIVE" and approved=="NO")
            flag=flag if fresh and consistent else ""
            if flag:
                evidence_source="FRESH_SFDC_EXPORT"
                evidence_when=cell(old,"Exported At KST")
        status="ACTIVE" if flag=="1" else "INACTIVE" if flag=="0" else "UNKNOWN"
        approved="YES" if flag=="1" else "NO" if flag=="0" else "UNVERIFIED"
        manual=bool(overrides.get(key,False))
        if manual:
            reason="MANUAL_EXCLUDED"
        elif flag=="0":
            reason="NOT_ACTIVE"
        elif flag=="1":
            reason=""
        else:
            reason="ACTIVE_NOT_VERIFIED"
        detail=quote_detail(detail_by_qid.get(qid,[])) if verified_mail else quote_detail([])
        amount=amount_by_sid.get(sid)
        output[key]={
            "Source Key":key,
            "Week Start":week,
            "Approval KST":cell(row,"Approval KST"),
            "Quote Name":cell(row,"Quotation Name"),
            "SFDC Record ID":sid,
            "Quote Status":status,
            "Approved AND Active":approved,
            "SFDC IsActive":flag or "UNVERIFIED",
            "Active Evidence Source":evidence_source or "NO_VALUE",
            "Active Evidence KST":evidence_when,
            "Chart Window":("RECENT_4_PLUS_CURRENT" if week in shown_weeks else "HISTORY"),
            **detail,
            "참고 금액 K USD":round(float(amount)/1000,4) if amount is not None else None,
            "참고 견적 USD":("USD "+format(amount,"f") if amount is not None
                             else "NO_VALUE"),
            "금액 근거":("SOURCE_QQ_PROCESS_OWNER_PARITY" if amount is not None
                        else "NO_VALUE"),
            "합산 상태":NOT_INCLUDED if reason else INCLUDED,
            "제외 이유":reason,
        }
    print("QUOTE_REVIEW_SOURCE_PASS total="+str(len(output))
          +" included="+str(sum(r["합산 상태"]==INCLUDED for r in output.values()))
          +" excluded="+str(sum(r["합산 상태"]==NOT_INCLUDED for r in output.values()))
          +" active_unverified="+str(sum(r["제외 이유"]=="ACTIVE_NOT_VERIFIED" for r in output.values()))
          +" active_evidence="+("QQ_3REPORT_VERIFIED" if verified_mail else "FALLBACK_OR_NO_VALUE")
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
        if value is None and observed in (None,"",[]):
            continue
        if isinstance(value,(int,float)) and not isinstance(value,bool):
            try:
                if abs(float(observed)-float(value))<0.00005:
                    continue
            except (ValueError,TypeError):
                pass
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
