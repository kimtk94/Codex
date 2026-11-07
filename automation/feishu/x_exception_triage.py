#!/usr/bin/env python3
"""Auditable X-project exception triage from Feishu Online state and dated notes.

Never assert that a dated note is the last record edit. A source snapshot can
be current while its narrative contains old dates, so note recency is explicitly
only a weak review signal. Do not infer payment/physical completion from either.
"""
import datetime as dt
import re

STATUS_FINAL={"settled","project completed"}
STATUS_START={"awaiting feedback(project start)"}
STATUS_STALL={"resending sample","resend samples","add-seq"}
STATUS_PAYMENT={"waiting po/payment","waiting for settlement"}
DETAIL_DATE=re.compile(
    r"(?<![A-Za-z0-9])(?:(20\d{2})[-./])?(0?[1-9]|1[0-2])[-./]"
    r"(0?[1-9]|[12]\d|3[01])(?!\d)"
)
QC_RISK=re.compile(r"产率很低|污染|index异常|qPCR\s*=\s*0|样本破损|爆管|low\s*yield|contaminat",re.I)
RESEQ=re.compile(r"加测|重上机|重测|re.?sequenc",re.I)
SAMPLE_RESEND=re.compile(r"重送|补送|re.?send",re.I)

def latest_dated_note(text,asof):
    """Latest recognizable date in a free-text history; not an edit timestamp."""
    found=[]
    for match in DETAIL_DATE.finditer(str(text or "")):
        year,month,day=match.groups()
        yy=int(year or asof.year)
        mm,dd=int(month),int(day)
        try:date=dt.date(yy,mm,dd)
        except ValueError:continue
        if not year and date>asof:
            # An upcoming 12.12 is not proof of an event in last December.
            # Only infer previous year at the Jan/Feb crossover.
            if not (asof.month<=2 and mm>=11):
                continue
            try:date=dt.date(yy-1,mm,dd)
            except ValueError:continue
        if date>asof or (asof-date).days>366:continue
        found.append((date,bool(year)))
    if not found:return None,"NO_DATED_EVENT"
    value=max(row[0] for row in found)
    explicit=any(day==value and is_explicit for day,is_explicit in found)
    return value,("EXPLICIT_DATE_IN_NARRATIVE" if explicit else
                   "YEAR_INFERRED_FROM_SNAPSHOT")

def parse_remaining(raw):
    s=str(raw or "").strip()
    if not re.fullmatch(r"[+-]?\d+(?:\.0+)?",s):return None
    return int(float(s))

def classify(row,asof):
    """One deterministic action-oriented classification per real X record."""
    status=str(row.get("Project Status") or "").strip()
    lower=status.casefold()
    remarks=str(row.get("remark") or "")
    progression=str(row.get("Progression Details") or "")
    notes=" ".join((progression,
                    str(row.get("Special Progression Details") or ""),
                    str(row.get("TS/AM update") or "")))
    dt_found,basis=latest_dated_note(notes,asof)
    days=(asof-dt_found).days if dt_found else None
    remaining=parse_remaining(row.get("Remaining Lead Time-Calendar Days"))
    ended=lower in STATUS_FINAL
    codes=[]
    reasons=[]
    severity=0
    action=[]
    def add(code,level,why,step):
        nonlocal severity
        if code in codes:return
        codes.append(code);reasons.append(why);action.append(step)
        severity=max(severity,level)

    if not ended:
        if remaining is not None and remaining<0:
            add("TAT_NEGATIVE",3,"잔여 TAT 음수: 일정 기준 확인 필요",
                "실제 약속 TAT와 지연 사유 확인")
        if lower=="abnormal":
            add("ABNORMAL_STATUS",3,"Feishu 상태 Abnormal",
                "원인·재작업 범위와 고객 안내 여부 확인")
        if lower in STATUS_STALL:
            code="RESEND_PENDING" if "resend" in lower else "ADD_SEQ_PENDING"
            add(code,2,"시료 재제출/추가 시퀀싱 단계",
                "재제출 또는 추가 시퀀싱 완료·다음 일정 확인")
        if lower in STATUS_START:
            add("START_CONFIRM_PENDING",2 if days is not None and days>=14 else 1,
                "프로젝트 시작 관련 회신 대기","고객·생산팀의 시작 확인 및 다음 조치 점검")
        if lower=="awaiting feedback(bi form)":
            add("BIF_PENDING",2,"BI Form 회신 대기","BIF 제출·접수 여부 확인")
        if lower=="waiting sequencing":
            add("WAITING_SEQUENCING",2 if (days is not None and days>=21) or
                remaining is not None and remaining<=7 else 1,
                "시퀀싱 대기","배치·상차 예정일과 잔여 TAT 확인")
        if lower=="waiting po/payment":
            add("PO_PAYMENT_PENDING",2,"PO 또는 결제 확인 대기",
                "계약별 PO 접수·Payment 증빙 확인")
        if lower=="waiting for settlement":
            add("STATEMENT_PENDING",2 if days is not None and days>=21 else 1,
                "Statement 정산 대기","Statement 확인 및 Invoice/Receipt 연결 점검")
        # Historical text flags are review hints, not proof of unresolved errors.
        if QC_RISK.search(notes) and lower in (
            "abnormal","add-seq","resending sample","resend samples",
            "data qc","sample qc"):
            add("QC_RISK_NOTE",2,"진행 메모에 QC·산출량 이슈 언급",
                "문제 발생 이후 재검 결과·해결 여부 확인")
        if SAMPLE_RESEND.search(notes) and lower not in STATUS_STALL:
            add("RESEND_IN_HISTORY",1,"과거 메모에 재제출 언급",
                "재제출 이력이 현재 프로젝트에 영향 있는지 확인")
        if RESEQ.search(notes) and lower not in STATUS_STALL:
            add("RESEQ_IN_HISTORY",1,"과거 메모에 추가 시퀀싱 언급",
                "추가 생산 이력이 완료됐는지 확인")
        if days is not None and days>=30:
            add("DATED_NOTE_30D",2,
                "최근 날짜가 적힌 메모가 30일 이상 전",
                "Feishu 실제 마지막 수정일과 최신 상태를 확인")
        elif days is not None and days>=14:
            add("DATED_NOTE_14D",1,
                "최근 날짜가 적힌 메모가 14일 이상 전",
                "최신 단계 메모가 별도로 있는지 확인")
        if remaining is None and lower not in STATUS_START:
            add("TAT_NOT_AVAILABLE",1,"잔여 TAT 미확인",
                "해당 단계에 TAT가 적용되는지 확인")
    else:
        # A project's "Settled" label is not bank receipt evidence.
        add("STATUS_FINAL_REVIEW",1,"종료/정산 상태; 입금 완료 증빙과 별개",
            "정확한 CMS Invoice 및 Receipt 확인")
    priority={3:"P0_URGENT",2:"P1_REVIEW",1:"P2_WATCH",0:"NORMAL"}[severity]
    age_state=("NO_DATED_NOTE" if days is None else
               "DATED_NOTE_30D_PLUS" if days>=30 else
               "DATED_NOTE_14_29D" if days>=14 else
               "DATED_NOTE_RECENT")
    tat_state=("TAT_NOT_VERIFIED" if remaining is None else
               "TAT_NEGATIVE" if remaining<0 else
               "TAT_ZERO" if remaining==0 else
               "TAT_1_7D" if remaining<=7 else "TAT_POSITIVE")
    return {
        "Exception Priority":priority,
        "Attention State":"REVIEW_REQUIRED" if severity>=2 else (
            "MONITOR" if severity==1 else "NO_EXCEPTION"),
        "Exception Codes":";".join(codes),
        "Primary Reason":reasons[0] if reasons else "검토 필요 신호 없음",
        "Exception Detail":" | ".join(reasons)[:1900],
        "Suggested Check":"; ".join(action[:3]) if action else "정기 상태 확인",
        "Last Dated Note":dt_found.isoformat() if dt_found else "",
        "Note Age Days":days,
        "Dated Note Age Flag":age_state,
        "Note Date Basis":basis,
        "TAT Risk":tat_state,
        "Audit As Of":asof.isoformat(),
    }

EXCEPTION_SCHEMA=[
    ("Exception Priority",1),("Attention State",1),("Exception Codes",1),
    ("Primary Reason",1),("Exception Detail",1),("Suggested Check",1),
    ("Last Dated Note",1),("Note Age Days",2),("Dated Note Age Flag",1),
    ("Note Date Basis",1),("TAT Risk",1),("Audit As Of",1),
]
