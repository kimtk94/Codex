#!/usr/bin/env python3
"""Month-indexed Actual/Pending/Forecast from the linked project lifecycle.

Invoice numbers: actual only. Original unissued J Statements: pending only.
Unbilled projects without Statement: estimate only. No duplicate X forecasts.
Only >=2026-10 is treated as covered by this validated new QQ source.
"""
import datetime as dt
import re
import sys

import incremental_sync as css
from tax_invoice_extract import extract
from unified_followup_sync import DST, SRC, KST, get, put

TAB="BI Revenue Lifecycle Monthly"
HEAD=["Month","Actual Invoice KRW","Pending Verified KRW","Forecast KRW",
      "Combined KRW (verified + estimate)","Invoice Count","Open Statement Count",
      "Pending Amount Unknown","Forecast Projects","Partial Billing Reviews",
      "Data Quality","Snapshot KST"]
ALLOWED={"FILENAME_PARSED","VERIFIED_LEGACY_FILENAME","EXISTS_IN_LEGACY"}
FIRST="2026-10"

def cell(r,n):
    return str(r[n]) if n<len(r) and r[n] is not None else ""

def month_of(v):
    if not v:return ""
    try:
        return dt.datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(KST).strftime("%Y-%m")
    except ValueError:
        return ""

def compute(invoice_rows,lifecycle_rows,now):
    invoices={}
    for row in invoice_rows[1:]:
        number=cell(row,0)
        if cell(row,10) not in ALLOWED or not re.fullmatch(r"209126\d{6}",number):
            continue
        subject=cell(row,6)
        if re.match(r"^\s*(?:re|fw|fwd|회신|답장|전달)\s*[:：]",subject,re.I):
            continue
        if not re.match(r"^\s*❗?\ufe0f?\s*Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b",subject,re.I):
            continue
        result=extract(cell(row,5))
        if not result or result[4] is None:continue
        try:amount=int(cell(row,1))
        except ValueError:continue
        if number!=result[0] or amount!=result[4] or amount<=0:
            raise RuntimeError("Invoice filename amount mismatch: "+number)
        month=month_of(cell(row,7))
        if not month:raise RuntimeError("Unknown original invoice issue date: "+number)
        if month<FIRST:continue
        if number in invoices and invoices[number]!=(month,amount):
            raise RuntimeError("Duplicate invoice amount or date conflict: "+number)
        invoices[number]=(month,amount)

    buckets={}
    def bucket(month):
        if month not in buckets:
            buckets[month]={"actual":0,"invoice":0,"pending":0,"open":0,
                            "unknown":0,"forecast":0,"forecast_n":0,"partial":0}
        return buckets[month]
    for month,amount in invoices.values():
        p=bucket(month);p["actual"]+=amount;p["invoice"]+=1

    seen_projects=set()
    for row in lifecycle_rows[1:]:
        x=cell(row,0).upper()
        if not x:continue
        if x in seen_projects:raise RuntimeError("Duplicate project lifecycle row: "+x)
        seen_projects.add(x)
        billing=cell(row,16)
        month=cell(row,12)
        if not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])",month or ""):
            month=month_of(cell(row,21)) or "UNSCHEDULED"
        if month!="UNSCHEDULED" and month<FIRST:continue
        open_j=[j.strip() for j in cell(row,20).split("|") if j.strip()]
        p=bucket(month)
        if open_j:
            p["open"]+=len(open_j)
            label=cell(row,23)
            m=re.fullmatch(r"AMOUNT_VERIFIED (\d+)/(\d+)",label)
            verified_n=int(m.group(1)) if m else 0
            if not m or int(m.group(2))!=len(open_j) or verified_n>len(open_j):
                raise RuntimeError("Inconsistent pending verification status for "+x)
            p["unknown"]+=len(open_j)-verified_n
            pending_value=cell(row,22)
            if verified_n:
                try:value=int(float(pending_value))
                except ValueError:raise RuntimeError("Missing verified pending amount for "+x)
                if value<=0:raise RuntimeError("Nonpositive verified pending for "+x)
                p["pending"]+=value
        if "ISSUED" in billing and open_j:
            p["partial"]+=1
        if (not open_j and "ISSUED" not in billing and
            billing in ("PROJECT FORECAST","COMPLETED - STATEMENT NOT VERIFIED")):
            try:estimate=int(float(cell(row,17) or 0))
            except ValueError:estimate=0
            if estimate>0:
                p["forecast"]+=estimate
                p["forecast_n"]+=1

    stamp=now.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    rows=[HEAD]
    for month in sorted(buckets,key=lambda k:(k=="UNSCHEDULED",k)):
        p=buckets[month]
        if not any(p.values()):continue
        quality=("PENDING_AMOUNTS_UNVERIFIED" if p["unknown"]
                 else "INVOICES_VERIFIED_FORECAST_ESTIMATED")
        rows.append([month,p["actual"],p["pending"],p["forecast"],
                     p["actual"]+p["pending"]+p["forecast"],p["invoice"],
                     p["open"],p["unknown"],p["forecast_n"],p["partial"],
                     quality,stamp])
    if not rows[1:]:raise RuntimeError("No covered revenue rows")
    return rows

def main():
    s=css.authorize()
    invoices=get(s,SRC,"CSS Tax Invoice Extract","A1:L10000")
    lifecycle=get(s,DST,"BI Project Lifecycle Overview","A1:X1000")
    old=get(s,DST,TAB,"A1:L100")
    if not invoices or invoices[0][0]!="invoice_number":
        raise RuntimeError("Invoice source unavailable")
    if not lifecycle or lifecycle[0][0]!="Project / Sub-project" or len(lifecycle[0])!=24:
        raise RuntimeError("Lifecycle source not updated with pending amount evidence")
    if not old or old[0]!=HEAD:raise RuntimeError("Monthly revenue schema mismatch")
    rows=compute(invoices,lifecycle,dt.datetime.now(dt.timezone.utc))
    if len(rows)<len(old):
        raise RuntimeError("Refuse to shrink existing monthly revenue ledger")
    put(s,DST,TAB,"A1",rows,"RAW")
    check=get(s,DST,TAB,"A1:L"+str(len(rows)))
    if len(check)!=len(rows) or check[0]!=HEAD:
        raise RuntimeError("Monthly revenue write verification failed")
    oct_row=next((r for r in rows[1:] if r[0]=="2026-10"),None)
    if not oct_row:raise RuntimeError("October 2026 monthly evidence missing")
    stamp=dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    put(s,DST,"Automation Health","A16",[[
        "Revenue Lifecycle",stamp,"PASS",
        "oct_invoice_count="+str(oct_row[5])+
        " oct_actual_krw="+str(oct_row[1])+
        " oct_pending_verified_krw="+str(oct_row[2])+
        " oct_forecast_krw="+str(oct_row[3])+
        " unresolved_pending_count="+str(sum(r[7] for r in rows[1:]))
    ]],"RAW")
    print("REVENUE_LIFECYCLE_MONTHLY_PASS October_invoice_count="+str(oct_row[5])+
          " October_actual_krw="+str(oct_row[1])+
          " October_pending_verified_krw="+str(oct_row[2])+
          " October_forecast_krw="+str(oct_row[3])+
          " October_pending_unknown="+str(oct_row[7]),flush=True)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("REVENUE_LIFECYCLE_MONTHLY_FAILED "+type(exc).__name__,file=sys.stderr)
        raise
