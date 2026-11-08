"""Monthly VAT-aware revenue + weekly quote aggregates, source-backed only."""
import datetime as dt
import math
import re
from qq_mail_ingest import SafeError
from native_kpi_compute import val,SRC

def amount(v):
    try:
        x=float(val(v).replace(",","").replace("₩",""))
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):return None

def latest(rows,key,until):
    choices=[]
    for r in rows:
        x=val(r.get(key))
        pattern=r"\d{4}-\d{2}" if key=="Month" else r"\d{4}-\d{2}-\d{2}"
        limit=until.strftime("%Y-%m" if key=="Month" else "%Y-%m-%d")
        if re.fullmatch(pattern,x) and x<=limit:choices.append((x,r))
    if not choices:return None
    date=max(x for x,_ in choices)
    selected=[r for x,r in choices if x==date]
    if len(selected)==1:return selected[0]
    # Manual original eTax is a separate Source Key in the *same Month*, not
    # a duplicate of the canonical QQ-issued CMS source. Summation here
    # mirrors the native Feishu Revenue chart's SUM-by-Month behaviour.
    # Weekly Quote still forbids duplicate period rows.
    if key!="Month":
        raise SafeError("KPI_DUPLICATE_FINANCIAL_PERIOD")
    keys=[val(r.get("Source Key")) for r in selected]
    if len(set(keys))!=len(keys) or not all(
            k.startswith("INVOICE:"+date) or
            k.startswith("ERP_ETAX:"+date+":") for k in keys):
        raise SafeError("KPI_MONTHLY_UNKNOWN_OR_DUPLICATE_SOURCE_KEY")
    if sum(k.startswith("INVOICE:"+date) for k in keys)!=1:
        raise SafeError("KPI_MONTHLY_QQ_CANONICAL_NOT_UNIQUE")
    total={"Month":date}
    for name in ("Net Revenue KRW Ex VAT","Net Revenue K USD",
                 "Tax Invoice KRW Incl VAT","Invoice Count"):
        numbers=[amount(r.get(name)) for r in selected]
        if any(n is None or n<0 for n in numbers):
            raise SafeError("KPI_MONTHLY_INCOMPLETE_SOURCE_AMOUNT")
        subtotal=sum(numbers)
        total[name]=int(subtotal) if name=="Invoice Count" else subtotal
    total["Coverage Status"]=";".join(sorted(
        {val(r.get("Coverage Status")) for r in selected}))
    print("KPI_MONTHLY_MULTISOURCE_SUM month="+date+
          " contributing_keys="+str(len(keys))+
          " issued_eTax_documents="+str(total["Invoice Count"])+
          " net_krw="+str(int(total["Net Revenue KRW Ex VAT"]))+
          " other_periods_unchanged=true",flush=True)
    return total

def financial(source,links,now):
    rows=[];stamp=now.strftime("%Y-%m-%d %H:%M KST")
    def add(k,g,title,field,unit,period,status,note,origin):
        n=amount(field)
        if n is None:return
        rows.append({"KPI Key":k,"섹션":g,"지표":title,"값":n,"단위":unit,
                     "기간":period,"검증 상태":status,"상세 설명":note,
                     "원본 화면":links[origin],"갱신 시각":stamp})
    m=latest(source[SRC[3]],"Month",now)
    if m:
        p=val(m.get("Month"));coverage=val(m.get("Coverage Status"))
        status="REVIEW" if not coverage or "REVIEW" in coverage.upper() else "SOURCE_BACKED"
        for k,title,field,unit in (
            ("NET_KRW","Revenue VAT 제외","Net Revenue KRW Ex VAT","KRW"),
            ("NET_KUSD","Revenue VAT 제외","Net Revenue K USD","K USD"),
            ("GROSS","Tax Invoice VAT 포함","Tax Invoice KRW Incl VAT","KRW"),
            ("COUNT","Tax Invoice 건수","Invoice Count","건")):
            add("MONTH_"+k,"04 매출",title,m.get(field),unit,p,status,
                "VAT 기준 구분 필수. 원본 커버리지: "+coverage,SRC[3])
    w=latest(source[SRC[4]],"Week Start",now)
    if w:
        p=val(w.get("Week Start"));code=val(w.get("Amount Status"))
        status="REVIEW" if "PARTIAL" in code or "NO_" in code or not code else "SOURCE_BACKED"
        for k,title,field,unit in (
            ("APPROVED","주간 Quote 승인","Approved Quote Count","건"),
            ("KRW","Quote 검증 금액 (환산)","Verified Quote Value KRW FX","KRW"),
            ("KUSD","Quote 검증 금액","Verified Quote Value K USD","K USD"),
            ("UNMATCHED","Quote 금액 미확인","Unmatched Amount Count","건")):
            add("WEEK_"+k,"05 견적",title,w.get(field),unit,p,status,
                "Quote는 실제 매출이 아니며 KRW는 FX 환산",SRC[4])
    return rows
