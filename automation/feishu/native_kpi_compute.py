"""Compute conservative Feishu KPI aggregates: no unverified mail replies or revenue."""
import collections
import datetime as dt
import re
from zoneinfo import ZoneInfo
from qq_mail_ingest import SafeError,plain_field,SMOKE_KEY
from mail_classification_2026 import since_2026
KST=ZoneInfo("Asia/Seoul")
SRC=("QQ Mail Intake","Mail Identity 2026","Project SIF Monitor","Monthly Tax Invoice","Weekly Quote KPI")
VIEWS=("현재 메일 · 최근 30일","전체 메일 연결","프로젝트 진행 · SIF","월별 Tax Invoice","매주 Quote 건수 · 금액")
def val(v):
    return str(v) if isinstance(v,(int,float)) else plain_field(v).strip()
def dt_kst(v):
    try:
        d=dt.datetime.fromisoformat(val(v).replace("Z","+00:00"))
        return d.astimezone(KST) if d.tzinfo else None
    except (TypeError,ValueError,OverflowError):return None
def compute(source,links,now):
    out=[];day=now.strftime("%Y-%m-%d");stamp=now.strftime("%Y-%m-%d %H:%M KST")
    def add(key,g,label,count,status,note,table):
        out.append({"KPI Key":key,"섹션":g,"지표":label,"값":count,"단위":"건",
                    "기간":day,"검증 상태":status,"상세 설명":note,
                    "원본 화면":links[table],"갱신 시각":stamp})
    mail=collections.Counter();seen=set()
    for r in source[SRC[0]]:
        k=val(r.get("Mail Key"))
        if k==SMOKE_KEY:continue
        if not re.fullmatch(r"[a-f0-9]{64}",k) or k in seen:raise SafeError("KPI_BAD_MAIL_KEY")
        seen.add(k)
        if not since_2026(val(r.get("Received At"))):continue
        mail["ALL"]+=1
        d=val(r.get("Direction"))
        if d in ("INBOUND","OUTBOUND"):mail[d]+=1
        t=dt_kst(r.get("Received At"))
        if t:mail["CURRENT" if t>=now-dt.timedelta(days=30) else "HISTORY"]+=1
    for k,label in (("ALL","수집 메일"),("INBOUND","수신 메일"),("OUTBOUND","발신 메일"),
                    ("CURRENT","최근 30일"),("HISTORY","2026년 과거")):
        add("MAIL_"+k,"01 메일",label,mail[k],"PARTIAL_ARCHIVE",
            "전체 2026년 메일 수집 완료 전; Feishu 적재분",SRC[0])
    idx=collections.Counter();seen=set()
    for r in source[SRC[1]]:
        k=val(r.get("Mail Key"))
        if not re.fullmatch(r"[a-f0-9]{64}",k) or k in seen:raise SafeError("KPI_BAD_IDENTITY_KEY")
        seen.add(k);idx["ALL"]+=1
        idx["STATE_"+val(r.get("Relationship Status"))]+=1
        idx["POOL_"+val(r.get("Followup Pool"))]+=1
        if val(r.get("Contact Link"))=="EMAIL_EXACT_CONTACT":idx["CONTACT"]+=1
        if val(r.get("Project Link"))=="PROJECT_ID_EXACT":idx["PROJECT"]+=1
    if idx["ALL"]>mail["ALL"]:raise SafeError("KPI_IDENTITY_GT_MAIL")
    state="SOURCE_LAG" if idx["ALL"]<mail["ALL"] else "SOURCE_BACKED"
    for k,label in (("POOL_THREAD_REVIEW_REQUIRED","고객 답변 검토"),
                    ("CONTACT","Contact 정확 연결"),("PROJECT","Project 정확 연결"),
                    ("STATE_LINKED","연결 확정"),("STATE_REVIEW","연결 검토")):
        add("IDENTITY_"+k,"02 고객·프로젝트",label,idx[k],state,
            "답변 검토는 미응답 확정이 아님",SRC[1])
    sif=source[SRC[2]];counts=collections.Counter(val(r.get("SIF State")) for r in sif)
    for k,label,n in (("ROWS","SIF 모니터 적재",len(sif)),
                      ("APPROVED","SIF 승인",counts["APPROVED"]),
                      ("REVIEW","SIF 미확인",counts["NOT_VERIFIED"])):
        add("SIF_"+k,"03 프로젝트",label,n,"PARTIAL_SOURCE","현재 적재분만 집계",SRC[2])
    print("DASHBOARD_COVERAGE mail="+str(mail["ALL"])+" identity="+str(idx["ALL"])+" "+state)
    return out
