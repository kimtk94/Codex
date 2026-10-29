"""Rank Lead outreach only from strict personal-sender QQ evidence.

This source is generated from the current SFDC Lead Report and
taehoon.kim@novogene.com To/CC matches. BCC and phone/visit not evidenced.
"""
from datetime import date,datetime
from today_action_top10 import clean

VALID = {"NO_PERSONAL_OUTBOUND_EVIDENCE","SENT_BEFORE_LEAD_ONLY"}
CONTACTED = "SENT_AFTER_LEAD_CONFIRMED"
CLOSED = {"QUALIFIED","CONVERTED","CLOSED","UNQUALIFIED"}


def created_date(s):
    s=clean(s)
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    try:
        return datetime.strptime(s,"%m/%d/%Y").date()
    except ValueError:
        return None


def personal_lead_rows(records,today):
    if not records or len(records)<450:
        raise ValueError("Personal Lead audit incomplete, refusing pool write")
    required=("Lead ID","Created Date","Email","My Mail Status",
              "Description Class","Lead Status","Opportunity ID")
    if not all(k in records[0] for k in required):
        raise ValueError("Personal Lead audit schema is incomplete")
    ids=set()
    results=[]
    for r in records:
        rid=clean(r.get("Lead ID"))
        if not rid or rid.upper() in ids:
            raise ValueError("Blank or duplicate personal Lead ID")
        ids.add(rid.upper())
        status=clean(r.get("My Mail Status")).upper()
        if status not in VALID|{CONTACTED}:
            raise ValueError("Unknown personal Lead mail status for "+rid+": "+status)
        if status==CONTACTED:
            continue
        if clean(r.get("Lead Status")).upper() in CLOSED or clean(r.get("Opportunity ID")):
            continue
        email=clean(r.get("Email")).lower()
        when=created_date(r.get("Created Date"))
        if not email or "@" not in email or not when:
            raise ValueError("Personal Lead missing email or created date "+rid)
        description=clean(r.get("Description"))
        has_desc=clean(r.get("Description Class")).upper()=="PRESENT" and len(description)>4
        age=max(0,(today-when).days)
        if age<=7: score=85 if has_desc else 62
        elif age<=30: score=76 if has_desc else 57
        elif age<=90: score=56 if has_desc else 34
        else: score=38 if has_desc else 18
        prior=status=="SENT_BEFORE_LEAD_ONLY"
        if prior:score=max(10,score-6)
        priority="P0" if score>=85 else "P1" if score>=55 else "P2"
        action=("과거 메일 이후 신규 Lead: 최근 연락 이력 확인 후 재연락" if prior else
                "문의 내용 기반 개별 답변 준비, 전화·방문 이력 확인" if has_desc else
                "Description 없음: 접촉 이력 확인 후 개별/BCC 발송 방식 검토")
        results.append({"Priority":priority,"Score":score,
            "Source":"LEAD","Record ID":rid,
            "Institution":clean(r.get("Institution")),
            "Customer":clean(r.get("Customer")),
            "Project ID":"",
            "Issue":description[:160] if has_desc else "Description 없음 — 서비스/연락 의사 확인",
            "Action":action,"Due Date":when.isoformat(),
            "Final Contact Date":clean(r.get("Last Sent After Lead")),
            "Verification":status,
            "Evidence":email,
            "Source Tab":"Lead My Sent Audit"})
    return results
