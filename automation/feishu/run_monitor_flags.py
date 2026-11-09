#!/usr/bin/env python3
"""Pure, fail-closed progress flags and daily cron watch for CSS Actions.

A GitHub SUCCESS by itself does not imply source/sink PASS.
No writes to sales source files, payments or customer records.
"""
import datetime as dt

GRACE_MINUTES=45
KST=dt.timezone(dt.timedelta(hours=9))

SFDC_PHASES=(
    ("source","Read authorized subscription mail and conditionally stage"),
    ("freshness","Check current 09/12/17 report slot after staging"),
    ("quote","Publish only SFDC Quote Review and Weekly KPI"),
    ("chart","Refresh and verify native Quote trend dashboards"),
)
FEISHU_PHASES=("tests","ingest","lifecycle","payment","monthly")


def status_of(entry):
    conclusion=entry.get("conclusion")
    state=entry.get("status")
    if conclusion=="success":
        return "PASS"
    if conclusion in ("failure","cancelled","timed_out","action_required"):
        return "FAIL"
    if state in ("in_progress","completed","waiting"):
        return "RUNNING" if state!="completed" else "CHECK"
    if state in ("queued","pending","requested"):
        return "WAIT"
    return "WAIT"


def stage_flags(label,run,jobs,source,sink):
    """Return explicit START / MIDDLE / COMPLETE flags plus active work.

    Feishu stages are parallel after source ingest: payment, lifecycle and
    monthly can be in progress simultaneously, never a fictional linear order.
    """
    state=run.get("status")
    has_started=state in ("in_progress","completed","waiting")
    start="PASS" if has_started else "WAIT"
    middle="WAIT"
    complete="WAIT"
    current="시작 대기"
    detail={}
    if label=="SFDC Report":
        for name,needle in SFDC_PHASES:
            matched=[step for job in jobs for step in job.get("steps") or []
                     if needle in (step.get("name") or "")]
            if len(matched)>1:
                raise ValueError("DUPLICATE_SFDC_STAGE_"+name)
            detail[name]=status_of(matched[0]) if matched else "WAIT"
        if detail["freshness"]=="PASS":
            middle="PASS"
        elif any(detail[k] in ("PASS","RUNNING") for k in ("source","freshness","quote")):
            middle="RUNNING"
        if state!="completed":
            current=next((
                name+" 진행 중" for name in ("source","freshness","quote","chart")
                if detail[name]=="RUNNING"),"GitHub 작업 시작·대기")
        else:
            current="최종 결과 확인 중"
    else:
        for name in FEISHU_PHASES:
            matched=[job for job in jobs if job.get("name")==name]
            if len(matched)>1:
                raise ValueError("DUPLICATE_FEISHU_JOB_"+name)
            detail[name]=status_of(matched[0]) if matched else "WAIT"
        if detail["ingest"]=="PASS":
            middle="PASS"
        elif detail["ingest"]=="RUNNING":
            middle="RUNNING"
        active=[name for name in ("ingest","lifecycle","payment","monthly")
                if detail[name]=="RUNNING"]
        current=(", ".join(active)+" 진행 중") if active else (
            "GitHub 테스트·수집 대기" if state!="completed" else "최종 결과 확인 중")
    if state=="completed" and source=="PASS" and sink=="PASS":
        complete="PASS"
        phase="완료"
        current="원본·목적지 검증 완료"
    elif state=="completed" or run.get("conclusion") in ("failure","cancelled","timed_out"):
        complete="BLOCK"
        phase="차단"
        failed=[k for k,v in detail.items() if v=="FAIL"]
        current="실패: "+", ".join(failed) if failed else "원본 또는 목적지 검증 미통과"
    elif middle in ("RUNNING","PASS"):
        phase="중간"
    else:
        phase="시작"
    if phase=="차단" and middle=="WAIT":
        middle="BLOCK"
    # Do not show a completed signal from a green GitHub run without proof.
    progress={"시작":"1/3" if has_started else "0/3",
              "중간":"2/3","완료":"3/3","차단":"BLOCK"}[phase]
    return {
        "진행 단계":phase,"진행률":progress,"시작 FLAG":start,
        "중간 FLAG":middle,"완료 FLAG":complete,"현재 작업":current,
        "단계별 결과":" / ".join(k+"="+v for k,v in detail.items()),
    }


def slots_from_clock(value):
    slots=set()
    for item in value.split(","):
        part=item.strip()
        pieces=part.split(":")
        if len(pieces)!=2 or not all(p.isdigit() for p in pieces):
            raise ValueError("INVALID_SCHEDULE_CLOCK")
        h,m=map(int,pieces)
        if h not in range(24) or m not in range(60):
            raise ValueError("INVALID_SCHEDULE_CLOCK")
        slots.add((h,m))
    if not slots:
        raise ValueError("EMPTY_SCHEDULE_CLOCK")
    return sorted(slots)


def latest_scheduled_slot(now,activated_at,clock):
    """Only consider slots after the workflow's last schedule definition update."""
    if now.tzinfo is None or activated_at.tzinfo is None:
        raise ValueError("NAIVE_SCHEDULE_TIME")
    today=now.astimezone(KST).date()
    activation=activated_at.astimezone(KST)
    candidates=[]
    for offset in range(3):
        day=today-dt.timedelta(days=offset)
        for hour,minute in slots_from_clock(clock):
            when=dt.datetime(day.year,day.month,day.day,hour,minute,tzinfo=KST)
            if activation<=when<=now:
                candidates.append(when)
    return max(candidates) if candidates else None


def watch_schedule(now,activated_at,clock,runs):
    """Unknown until scheduled slot matures; manual/push does not substitute.

    GitHub scheduled runs may be delayed. Match only the latest due slot and
    avoid older runs being mistaken for the latest slot's execution.
    """
    slot=latest_scheduled_slot(now,activated_at,clock)
    if not slot:
        return "WAIT_FIRST_SLOT",None,None
    due=slot.astimezone(dt.timezone.utc)
    matching=[]
    for r in runs:
        if r.get("event")!="schedule" or r.get("head_branch")!="main":
            continue
        raw=r.get("created_at")
        if not raw:
            continue
        started=dt.datetime.fromisoformat(str(raw).replace("Z","+00:00"))
        if due<=started<=now:
            matching.append((started,r))
    if matching:
        started,run=min(matching,key=lambda item:item[0])
        lag=(started-due).total_seconds()/60
        if run.get("conclusion") in ("failure","cancelled","timed_out"):
            return "RUN_FAILED",slot,run
        if run.get("status")!="completed":
            return "RUNNING",slot,run
        if lag>GRACE_MINUTES:
            return "LATE",slot,run
        return "EXECUTED",slot,run
    elapsed=(now-due).total_seconds()/60
    return ("SCHEDULE_MISSING" if elapsed>GRACE_MINUTES else "DUE_WAITING"),slot,None
