#!/usr/bin/env python3
"""Reconcile confirmed QQ approval mail into transient Weekly Quote evidence.

Never overwrite the canonical Google Sheet 'Quote Approval Dedup'. All
enrichment is in memory before Feishu KPI / review calculation. Require
latest authenticated SFDC QQ 3-report, immutable Salesforce Quote ID,
one QID->Opportunity mapping and Opportunity Owner exactly Kim Taehoon.
APPROVED_TEXT does not by itself prove Active or any money amount.
"""
import collections
import datetime as dt
from zoneinfo import ZoneInfo
from quote_process_amount import sf15,quote_id,week_for,validate_source,cell,MY_SALES_OWNER

KST=ZoneInfo("Asia/Seoul")

def stamp(raw):
    val=str(raw or "").strip().replace(" KST","").replace("Z","+00:00")
    if not val:
        return None
    try:
        when=dt.datetime.fromisoformat(val)
    except ValueError:
        return None
    if when.tzinfo is None:
        when=when.replace(tzinfo=KST)
    return when.astimezone(KST)

def supplement(source,now=None,window_days=21):
    now=now or dt.datetime.now(KST)
    if now.tzinfo is None:raise RuntimeError("APPROVAL_RECONCILE_TIMEZONE_REQUIRED")
    current=list(source.get("Quote Approval Dedup",[]))
    auto=source.get("Quotation Approval Auto",[])
    if not auto:
        print("QUOTE_APPROVAL_AUTO_NO_NEW_SOURCE",flush=True)
        return current,{"added":0,"reason":"AUTO_SOURCE_EMPTY"}
    if validate_source(source,now)!="SOURCE_QQ_REPORT_VERIFIED":
        print("QUOTE_APPROVAL_AUTO_WITHHELD_UNVERIFIED_SFDC_REPORT",flush=True)
        return current,{"added":0,"reason":"SFDC_REPORT_NOT_VERIFIED"}
    current_sid={}
    current_qid={}
    for row in current:
        sid=sf15(cell(row,"SFDC Record ID"))
        qid=quote_id(cell(row,"Quotation Name"))
        if not sid or not qid:
            continue
        if sid in current_sid and current_sid[sid]!=qid:
            raise RuntimeError("APPROVAL_DEDUP_SFID_CONFLICT")
        if qid in current_qid and current_qid[qid]!=sid:
            raise RuntimeError("APPROVAL_DEDUP_QID_CONFLICT")
        current_sid[sid]=qid
        current_qid[qid]=sid
    raw=collections.defaultdict(set)
    for row in source.get("SFDC Email Quotation Raw",[]):
        qid=quote_id(cell(row,"SFDC Quotation ID"))
        oid=cell(row,"Opportunity ID")
        if qid and oid:raw[qid].add(oid)
    owner=collections.defaultdict(set)
    for row in source.get("SFDC Email Opportunities Raw",[]):
        oid=cell(row,"Opportunity ID")
        if oid:owner[oid].add(cell(row,"Opportunity Owner"))
    added=0
    counts=collections.Counter()
    used_ingest=set()
    for row in sorted(auto,key=lambda r:cell(r,"approval_mail_at_kst")):
        if cell(row,"review_status")!="APPROVED" or cell(row,"approval_evidence")!="APPROVED_TEXT":
            counts["unapproved_or_unverified_mail"]+=1
            continue
        key=cell(row,"ingest_key")
        if not key or key in used_ingest:
            counts["duplicate_or_missing_ingest_key"]+=1
            continue
        used_ingest.add(key)
        when=stamp(cell(row,"approval_mail_at_kst"))
        if not when or not (dt.timedelta(0)<=now-when<=dt.timedelta(days=window_days)):
            counts["outside_recent_window"]+=1
            continue
        sid=sf15(cell(row,"salesforce_record_id"))
        qid=quote_id(cell(row,"quotation_name"))
        if not sid or not qid or not cell(row,"quotation_id").startswith("AMEA"):
            counts["invalid_immutable_approval_id"]+=1
            continue
        if sid in current_sid or qid in current_qid:
            counts["already_counted"]+=1
            if (sid in current_sid and current_sid[sid]!=qid) or (
                    qid in current_qid and current_qid[qid]!=sid):
                raise RuntimeError("APPROVAL_MAIL_CONFLICTS_CANONICAL_SFID")
            continue
        opps=raw.get(qid,set())
        if len(opps)!=1:
            counts["quote_to_opportunity_not_exact"]+=1
            continue
        if owner.get(next(iter(opps)),set())!={MY_SALES_OWNER}:
            counts["not_my_verified_opportunity"]+=1
            continue
        week=week_for(when.date().isoformat())
        if not week:
            raise RuntimeError("APPROVAL_WEEK_INVALID")
        start=dt.date.fromisoformat(week)
        last=start+dt.timedelta(days=6)
        item={
            "Approval KST":when.strftime("%Y-%m-%d %H:%M:%S"),
            "AMEA Quotation ID":cell(row,"quotation_id"),
            "Quotation Name":qid,
            "SFDC Record ID":sid,
            "Approval Evidence":"APPROVED_TEXT_QQ_MAIL",
            "Week Status":start.isoformat()+" ~ "+last.isoformat(),
            "Active":"UNVERIFIED",
            "Quote Status":"UNKNOWN",
            "Approved AND Active":"UNVERIFIED",
            "Currency":"",
            "Verified Amount kUSD":"",
        }
        current.append(item)
        current_sid[sid]=qid
        current_qid[qid]=sid
        added+=1
    stats={"added":added,"recent_approved_mail_candidates":sum(
           1 for x in auto if x.get("review_status")=="APPROVED"),
           "held":dict(counts),"canonical_rows_unchanged":len(source.get("Quote Approval Dedup",[])),
           "effective_approval_rows":len(current)}
    print("QUOTE_APPROVAL_MAIL_RECONCILED added="+str(added)+
          " existing="+str(stats["canonical_rows_unchanged"])+
          " effective="+str(stats["effective_approval_rows"])+
          " held="+str(dict(counts))+" source_sheet_writes=0",flush=True)
    return current,stats
