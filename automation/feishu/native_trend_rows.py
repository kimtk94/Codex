"""Build chart-ready, source-backed rows for Feishu native monthly and weekly trends."""
import datetime as dt
import math
import re
from zoneinfo import ZoneInfo
from qq_mail_ingest import SafeError,plain_field
KST=ZoneInfo("Asia/Seoul")
MONTH="Monthly Tax Invoice"
WEEK="Weekly Quote KPI"
FIELDS={
    "원본 키":1,"유형":1,"기간":1,"연도":2,
    "Revenue KRW VAT 제외":2,"Invoice KRW VAT 포함":2,"Revenue K USD":2,
    "Invoice 건수":2,"Quote 승인":2,"Quote KRW 환산":2,
    "Quote K USD":2,"Quote 금액 미확인":2,
    "증빙 상태":1,"원본 화면":1,"갱신 시각":1,
}
def val(v):
    return str(v) if isinstance(v,(int,float)) else plain_field(v).strip()
def number(v):
    try:
        n=float(val(v).replace(",","").replace("₩",""))
        return n if math.isfinite(n) else None
    except (TypeError,ValueError):return None
def make(source,links,now):
    rows=[]
    stamp=now.strftime("%Y-%m-%d %H:%M KST")
    seen=set()
    for x in source[MONTH]:
        period=val(x.get("Month"))
        if not re.fullmatch(r"\d{4}-\d{2}",period):continue
        try:
            d=dt.datetime.strptime(period+"-01","%Y-%m-%d").replace(tzinfo=KST)
        except ValueError:continue
        if d>now:continue
        key="M:"+period
        if key in seen:raise SafeError("TREND_DUPLICATE_MONTH")
        seen.add(key)
        coverage=val(x.get("Coverage Status"))
        evidence="REVIEW" if not coverage or "REVIEW" in coverage.upper() else "SOURCE_BACKED"
        row={"원본 키":key,"유형":"MONTHLY_REVENUE","기간":period,
             "연도":d.year,"증빙 상태":evidence,
             "원본 화면":links[MONTH],"갱신 시각":stamp}
        for label,field in (
            ("Revenue KRW VAT 제외","Net Revenue KRW Ex VAT"),
            ("Invoice KRW VAT 포함","Tax Invoice KRW Incl VAT"),
            ("Revenue K USD","Net Revenue K USD"),
            ("Invoice 건수","Invoice Count"),
        ):
            n=number(x.get(field))
            if n is not None:row[label]=n
        rows.append(row)
    for x in source[WEEK]:
        period=val(x.get("Week Start"))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",period):continue
        try:
            d=dt.datetime.strptime(period,"%Y-%m-%d").replace(tzinfo=KST)
        except ValueError:continue
        if d>now:continue
        key="W:"+period
        if key in seen:raise SafeError("TREND_DUPLICATE_WEEK")
        seen.add(key)
        status=val(x.get("Amount Status"))
        evidence="REVIEW" if not status or "PARTIAL" in status or "NO_" in status else "SOURCE_BACKED"
        row={"원본 키":key,"유형":"WEEKLY_QUOTE","기간":period,
             "연도":d.year,"증빙 상태":evidence,
             "원본 화면":links[WEEK],"갱신 시각":stamp}
        for label,field in (
            ("Quote 승인","Approved Quote Count"),
            ("Quote KRW 환산","Verified Quote Value KRW FX"),
            ("Quote K USD","Verified Quote Value K USD"),
            ("Quote 금액 미확인","Unmatched Amount Count"),
        ):
            n=number(x.get(field))
            if n is not None:row[label]=n
        rows.append(row)
    if not rows:raise SafeError("TREND_NO_SOURCE_ROWS")
    print("TREND_SOURCE_MONTHS="+str(sum(r["유형"]=="MONTHLY_REVENUE" for r in rows)))
    print("TREND_SOURCE_WEEKS="+str(sum(r["유형"]=="WEEKLY_QUOTE" for r in rows)))
    return rows
