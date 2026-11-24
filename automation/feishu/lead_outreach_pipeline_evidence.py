#!/usr/bin/env python3
"""Aggregate-only end-to-end evidence for SFDC/QQ -> Feishu Lead outreach refresh.

Consumes local step logs; rejects partial success and inconsistent counts.
Never stores Lead IDs, names, addresses, raw messages, subjects or mail text.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path

import lead_delta_evidence as delta

KST = dt.timezone(dt.timedelta(hours=9))

class EvidenceError(RuntimeError):
    pass

def line_values(text, marker):
    values = []
    for line in text.splitlines():
        if marker in line:
            values.append(line.split(marker, 1)[1].strip())
    return values

def one_json(text, marker, last=True):
    values = line_values(text, marker)
    if not values:
        raise EvidenceError("MISSING_STAGE_MARKER_" + marker.strip("= ").replace(" ", "_"))
    try:
        return json.loads(values[-1 if last else 0])
    except ValueError:
        raise EvidenceError("INVALID_JSON_MARKER_" + marker.strip("= ")) from None

def confirmed(text, marker):
    return bool(line_values(text, marker))

def require(ok, reason):
    if not ok:
        raise EvidenceError(reason)

def validate(personal_log, mirror_log, queue_log, views_log, delta_preview, delta_apply,
             now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    require(confirmed(personal_log, "PERSONAL_LEAD_AUDIT_APPLIED_AND_VERIFIED=true"),
            "PERSONAL_MAIL_SOURCE_NOT_VERIFIED")
    personal = one_json(personal_log, "PERSONAL_LEAD_AUDIT=")
    leads = personal.get("leads")
    states = personal.get("states") or {}
    require(type(leads) is int and leads >= 450, "LEAD_SOURCE_TOO_SMALL")
    required_states = ("SENT_AFTER_LEAD_CONFIRMED",
                       "SENT_BEFORE_LEAD_ONLY", "NO_PERSONAL_OUTBOUND_EVIDENCE")
    require(all(type(states.get(k)) is int and states[k]>=0 for k in required_states)
            and sum(states[k] for k in required_states)==leads,
            "PERSONAL_MAIL_STATUS_TOTAL_CONFLICT")
    try:
        observed = dt.datetime.fromisoformat(personal["latest_qq"].replace("Z","+00:00"))
    except (ValueError, TypeError, KeyError):
        raise EvidenceError("QQ_SOURCE_TIMESTAMP_INVALID") from None
    require(observed.tzinfo is not None, "QQ_SOURCE_TIMESTAMP_MISSING_ZONE")
    age = now - observed.astimezone(dt.timezone.utc)
    require(dt.timedelta(minutes=-5) <= age <= dt.timedelta(hours=72),
            "QQ_SOURCE_TIMESTAMP_STALE")

    require(confirmed(mirror_log, "FEISHU_LEAD_MAIL_DESCRIPTION_READBACK=PASS"),
            "FEISHU_MIRROR_NOT_VERIFIED")
    preserve = line_values(mirror_log, "LEAD_MANUAL_SELECTION_PRESERVED=")
    require(len(preserve)>=1 and preserve[-1].isdigit()
            and int(preserve[-1]) == leads, "LEAD_MANUAL_FLAGS_NOT_PRESERVED")
    mirror_plan = one_json(mirror_log, "LEAD_MAIL_DESCRIPTION_PLAN=")
    require(mirror_plan.get("total")==leads
            and mirror_plan.get("existing")==leads
            and mirror_plan.get("retained_not_deleted")==0, "FEISHU_MIRROR_COUNT_MISMATCH")

    require(confirmed(queue_log,"LEAD_QUEUE_READBACK_PASS=1 MODE=APPLY"),
            "FEISHU_ACTION_QUEUES_NOT_VERIFIED")
    q = one_json(queue_log, "LEAD_QUEUE_PLAN=")
    groups=q.get("groups") or {}
    cohort=q.get("eligibility") or {}
    age_counts=cohort.get("counts") or {}
    require(q.get("total")==leads
            and all(type(groups.get(k)) is int and groups[k]>=0 for k in
                    ("recontact","planned","review","none","expired"))
            and sum(groups.values())==leads, "QUEUE_PARTITION_MISMATCH")
    require(type(age_counts.get("eligible")) is int
            and type(age_counts.get("expired")) is int
            and sum(age_counts.values())==leads
            and groups["expired"]==age_counts["expired"],
            "ELIGIBILITY_TOTAL_MISMATCH")
    require(isinstance(cohort.get("cutoff"),str), "CUTOFF_MISSING")
    expected_contactable = q.get("eligible_no_evidence") or {}
    require(all(type(expected_contactable.get(k)) is int
                for k in ("description_present","description_missing")),
            "ELIGIBLE_MAIL_BREAKDOWN_MISSING")
    require(sum(expected_contactable.values())<=states["NO_PERSONAL_OUTBOUND_EVIDENCE"],
            "ELIGIBLE_UNSENT_EXCEEDS_PERSONAL_SOURCE")
    eligible_by_mail=q.get("eligible_mail_status") or {}
    require(all(type(eligible_by_mail.get(k)) is int and eligible_by_mail[k]>=0
                for k in ("after","prior_only","no_evidence"))
            and sum(eligible_by_mail.values())==age_counts["eligible"]
            and eligible_by_mail["no_evidence"]==sum(expected_contactable.values())
            and eligible_by_mail["after"]<=states["SENT_AFTER_LEAD_CONFIRMED"]
            and eligible_by_mail["prior_only"]<=states["SENT_BEFORE_LEAD_ONLY"],
            "ELIGIBLE_SENT_OUTBOUND_PARTITION_MISMATCH")

    require(confirmed(views_log, "LEAD_VIEW_AUDIT_PASS=1 MODE=APPLY"),
            "FEISHU_NO_EVIDENCE_VIEWS_NOT_VERIFIED")
    verified_views = [json.loads(value) for value in
                      line_values(views_log, "LEAD_VIEW_VERIFIED=")]
    selected = {item.get("view"):item.get("count") for item in verified_views}
    description_view = "01 · 발송 증거 없음 · Description 있음"
    common_view = "02 · 발송 증거 없음 · Description 없음"
    after_view = "06 · 최근 1년 · Lead 생성 후 발송 확인"
    before_view = "07 · 최근 1년 · Lead 생성 전만 발송"
    require(len(verified_views)==4 and len(selected)==4
            and selected.get(description_view)==expected_contactable["description_present"]
            and selected.get(common_view)==expected_contactable["description_missing"]
            and selected.get(after_view)==eligible_by_mail["after"]
            and selected.get(before_view)==eligible_by_mail["prior_only"],
            "OUTREACH_VIEW_ELIGIBILITY_MISMATCH")

    readback=delta.evidence(delta_preview,delta_apply,now=now)
    require(readback["result"] in ("PASS","NO_NEW_DATA"),
            "FINAL_DELTA_READBACK_UNVERIFIED")
    require(readback.get("plan",{}).get("records")==leads,
            "FINAL_DELTA_SOURCE_RECORD_MISMATCH")
    latest_counts=(readback.get("readback") or {}).get("counts_after")
    if latest_counts is None:
        latest_counts=(readback.get("no_new_data") or {}).get("counts")
    require(latest_counts and sum(latest_counts.values())==leads,
            "FINAL_DELTA_COUNT_MISMATCH")
    require(latest_counts["expired"]==age_counts["expired"],
            "FINAL_DELTA_EXPIRED_MISMATCH")

    return {
        "result":"PASS","source":"SFDC Lead / QQ personal sent evidence snapshot",
        "mirror":"Feishu dedicated Lead table",
        "evaluated_at":now.isoformat(),
        "qq_latest_mail_checked_at":personal["latest_qq"],
        "cutoff_kst":cohort["cutoff"],"lead_total":leads,
        "eligible":age_counts["eligible"],"excluded_over_one_year":age_counts["expired"],
        "sent_after_lead":states["SENT_AFTER_LEAD_CONFIRMED"],
        "sent_before_lead_only":states["SENT_BEFORE_LEAD_ONLY"],
        "no_personal_outbound_evidence":states["NO_PERSONAL_OUTBOUND_EVIDENCE"],
        "outreach_description_present":selected[description_view],
        "outreach_description_missing":selected[common_view],
        "recent_sent_after_lead":selected[after_view],
        "recent_sent_before_lead_only":selected[before_view],
        "sent_mail_views_verified":2,
        "action_queues":{k:groups[k] for k in ("recontact","planned","review","none","expired")},
        "mirror_readback":True,"manual_flags_preserved":True,
        "feishu_views_readback":True,
        "final_delta":readback["result"],
        "mail_sent_by_automation":False,"sfdc_writes":False,
        "pii_in_artifact":False,
    }

def main():
    parser = argparse.ArgumentParser()
    for name in ("personal","mirror","queue","views","preview","apply"):
        parser.add_argument("--"+name, required=True)
    parser.add_argument("--out",required=True)
    args=parser.parse_args()
    texts = [Path(getattr(args,k)).read_text(encoding="utf-8") for k in
             ("personal","mirror","queue","views","preview","apply")]
    result = validate(*texts)
    out=Path(args.out)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    summary=os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a",encoding="utf-8") as f:
            f.write("## Lead outreach end-to-end verification\n\n")
            f.write("| Key | Verified value |\n|---|---:|\n")
            for key in ("result","lead_total","eligible","excluded_over_one_year",
                        "sent_after_lead","sent_before_lead_only",
                        "no_personal_outbound_evidence","outreach_description_present",
                        "outreach_description_missing",
                        "recent_sent_after_lead","recent_sent_before_lead_only",
                        "cutoff_kst","final_delta"):
                f.write("| "+key+" | "+str(result[key])+" |\n")
            f.write("\nQQ/SFDC source re-evaluation → Feishu mirror → priority → "
                    "four classified Lead views → final delta parity. No sends; no SFDC writes.\n")
    print("LEAD_OUTREACH_PIPELINE_VERIFIED="+json.dumps({
        "result":result["result"],"leads":result["lead_total"],
        "eligible":result["eligible"],"excluded":result["excluded_over_one_year"],
        "first_email_candidates":result["outreach_description_present"]+
                                 result["outreach_description_missing"],
        "recent_sent_after":result["recent_sent_after_lead"],
        "recent_sent_before":result["recent_sent_before_lead_only"],
        "final_delta":result["final_delta"]},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
